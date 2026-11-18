// VRChat Avatar Studio - importa o .vrcavatar.json com validação profunda e rollback.
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;

namespace VRChatAvatarStudio.EditorTools
{
    public static class VASImporter
    {
        public const string DefaultRoot = "Assets/VRChatAvatars";
        const int MaxJsonBytes = 128 * 1024 * 1024;
        const int MaxTextureBytes = 16 * 1024 * 1024;
        const int MaxBones = 1024;
        const int MaxMeshes = 256;
        const int MaxVerticesPerMesh = 500000;
        const int MaxTrianglesPerMesh = 1000000;
        const int MaxPhysBones = 512;
        static readonly Dictionary<int, string> ImportedFolders = new Dictionary<int, string>();

        static bool Finite(float value) { return !float.IsNaN(value) && !float.IsInfinity(value); }
        static bool SafeIdentifier(string value) { return !string.IsNullOrEmpty(value) && Regex.IsMatch(value, @"^[A-Za-z0-9_\-]+$"); }
        static bool SafeShapeName(string value) { return !string.IsNullOrEmpty(value) && Regex.IsMatch(value, @"^[A-Za-z0-9_.\-]+$"); }

        public static VASAvatarData Load(string jsonPath)
        {
            if (string.IsNullOrEmpty(jsonPath) || !File.Exists(jsonPath))
                throw new FileNotFoundException("Arquivo .vrcavatar.json não encontrado.", jsonPath);
            var info = new FileInfo(jsonPath);
            if (info.Length <= 0 || info.Length > MaxJsonBytes)
                throw new InvalidDataException("O JSON está vazio ou excede o limite de 128 MB.");

            VASAvatarData data;
            try { data = JsonUtility.FromJson<VASAvatarData>(File.ReadAllText(jsonPath, Encoding.UTF8)); }
            catch (Exception e) { throw new InvalidDataException("Não foi possível interpretar o JSON: " + e.Message, e); }
            ValidateAvatarData(data);
            return data;
        }

        /// <summary>Valida a estrutura inteira antes de criar arquivos, assets ou objetos de cena.</summary>
        public static void ValidateAvatarData(VASAvatarData data)
        {
            var errors = new List<string>();
            if (data == null) throw new InvalidDataException("JSON vazio ou inválido.");
            if (data.format != "vrc-avatar-studio") errors.Add("format: formato não reconhecido");
            if (data.version != 1) errors.Add("version: versão não suportada (" + data.version + ")");
            if (string.IsNullOrWhiteSpace(data.name)) errors.Add("name: campo obrigatório ausente");
            if (!SafeTextureName(data.paletteTexture)) errors.Add("paletteTexture: deve ser apenas o nome de um PNG, sem diretórios");
            CheckVector(data.viewPosition, 3, "viewPosition", errors);

            if (data.bones == null || data.bones.Length == 0 || data.bones.Length > MaxBones)
                errors.Add("bones: quantidade inválida (esperado 1 a " + MaxBones + ")");
            if (data.meshes == null || data.meshes.Length == 0 || data.meshes.Length > MaxMeshes)
                errors.Add("meshes: quantidade inválida (esperado 1 a " + MaxMeshes + ")");

            var boneNames = new HashSet<string>(StringComparer.Ordinal);
            if (data.bones != null)
            {
                for (int i = 0; i < data.bones.Length; i++)
                {
                    var b = data.bones[i];
                    string prefix = "bones[" + i + "]";
                    if (b == null) { errors.Add(prefix + ": registro nulo"); continue; }
                    if (!SafeIdentifier(b.name)) errors.Add(prefix + ".name: identificador inválido");
                    else if (!boneNames.Add(b.name)) errors.Add(prefix + ".name: nome duplicado '" + b.name + "'");
                    if (b.parent < -1 || b.parent >= i) errors.Add(prefix + ".parent: índice inválido; pais devem aparecer antes do filho");
                    CheckVector(b.position, 3, prefix + ".position", errors);
                }
            }

            if (data.humanoid == null || data.humanoid.Length == 0) errors.Add("humanoid: mapeamento ausente");
            else
            {
                var humans = new HashSet<string>(StringComparer.Ordinal);
                for (int i = 0; i < data.humanoid.Length; i++)
                {
                    var h = data.humanoid[i];
                    if (h == null) { errors.Add("humanoid[" + i + "]: registro nulo"); continue; }
                    if (!SafeIdentifier(h.human) || !SafeIdentifier(h.bone)) errors.Add("humanoid[" + i + "]: nome de osso inválido");
                    else
                    {
                        if (!humans.Add(h.human)) errors.Add("humanoid[" + i + "]: humanName duplicado '" + h.human + "'");
                        if (!boneNames.Contains(h.bone)) errors.Add("humanoid[" + i + "]: bone inexistente '" + h.bone + "'");
                    }
                }
                string[] required = { "Hips", "Spine", "Head", "Neck", "LeftUpperArm", "RightUpperArm", "LeftLowerArm", "RightLowerArm",
                    "LeftHand", "RightHand", "LeftUpperLeg", "RightUpperLeg", "LeftLowerLeg", "RightLowerLeg", "LeftFoot", "RightFoot" };
                foreach (string h in required) if (!humans.Contains(h)) errors.Add("humanoid: mapeamento obrigatório ausente '" + h + "'");
            }

            if (data.eyes == null) errors.Add("eyes: objeto obrigatório ausente");
            else
            {
                if (string.IsNullOrEmpty(data.eyes.left) || !boneNames.Contains(data.eyes.left)) errors.Add("eyes.left: osso inexistente");
                if (string.IsNullOrEmpty(data.eyes.right) || !boneNames.Contains(data.eyes.right)) errors.Add("eyes.right: osso inexistente");
            }

            if (data.physbones != null)
            {
                if (data.physbones.Length > MaxPhysBones) errors.Add("physbones: excede " + MaxPhysBones + " componentes");
                for (int i = 0; i < data.physbones.Length && i < MaxPhysBones; i++)
                {
                    var pb = data.physbones[i];
                    if (pb == null) { errors.Add("physbones[" + i + "]: registro nulo"); continue; }
                    if (string.IsNullOrEmpty(pb.root) || !boneNames.Contains(pb.root)) errors.Add("physbones[" + i + "].root: osso inexistente");
                    if (pb.bones == null || pb.bones.Length == 0) errors.Add("physbones[" + i + "].bones: cadeia vazia");
                    else foreach (string n in pb.bones) if (string.IsNullOrEmpty(n) || !boneNames.Contains(n)) errors.Add("physbones[" + i + "].bones: referência inválida '" + n + "'");
                    if (pb.endpoint != null) CheckVector(pb.endpoint, 3, "physbones[" + i + "].endpoint", errors);
                }
            }

            if (data.meshes != null)
            {
                var meshNames = new HashSet<string>(StringComparer.Ordinal);
                long totalVertices = 0;
                for (int mi = 0; mi < data.meshes.Length; mi++)
                {
                    var m = data.meshes[mi];
                    string prefix = "meshes[" + mi + "]";
                    if (m == null) { errors.Add(prefix + ": registro nulo"); continue; }
                    if (!SafeIdentifier(m.name)) errors.Add(prefix + ".name: identificador inválido");
                    else if (!meshNames.Add(m.name)) errors.Add(prefix + ".name: nome duplicado '" + m.name + "'");
                    if (m.positions == null || m.positions.Length < 9 || m.positions.Length % 3 != 0)
                    { errors.Add(prefix + ".positions: precisa conter pelo menos 3 vértices XYZ"); continue; }
                    int vc = m.positions.Length / 3;
                    totalVertices += vc;
                    if (vc > MaxVerticesPerMesh) errors.Add(prefix + ".positions: excede " + MaxVerticesPerMesh + " vértices");
                    CheckFinite(m.positions, prefix + ".positions", errors);
                    if (m.normals == null || m.normals.Length != vc * 3) errors.Add(prefix + ".normals: tamanho deve ser vertices * 3");
                    else CheckFinite(m.normals, prefix + ".normals", errors);
                    if (m.uv == null || m.uv.Length != vc * 2) errors.Add(prefix + ".uv: tamanho deve ser vertices * 2");
                    else CheckFinite(m.uv, prefix + ".uv", errors);
                    if (m.triangles == null || m.triangles.Length < 3 || m.triangles.Length % 3 != 0)
                        errors.Add(prefix + ".triangles: índices devem formar triângulos completos");
                    else if (m.triangles.Length / 3 > MaxTrianglesPerMesh)
                        errors.Add(prefix + ".triangles: excede " + MaxTrianglesPerMesh + " triângulos");
                    else for (int k = 0; k < m.triangles.Length; k++)
                        if (m.triangles[k] < 0 || m.triangles[k] >= vc) { errors.Add(prefix + ".triangles[" + k + "]: índice fora dos vértices"); break; }
                    if (m.boneIndices == null || m.boneIndices.Length != vc * 4) errors.Add(prefix + ".boneIndices: tamanho deve ser vertices * 4");
                    if (m.boneWeights == null || m.boneWeights.Length != vc * 4) errors.Add(prefix + ".boneWeights: tamanho deve ser vertices * 4");
                    if (m.boneIndices != null && m.boneWeights != null && m.boneIndices.Length == vc * 4 && m.boneWeights.Length == vc * 4)
                    {
                        for (int v = 0; v < vc; v++)
                        {
                            float sum = 0f;
                            for (int j = 0; j < 4; j++)
                            {
                                int ix = v * 4 + j;
                                int bi = m.boneIndices[ix];
                                float w = m.boneWeights[ix];
                                if (bi < 0 || bi >= boneNames.Count) errors.Add(prefix + ".boneIndices[" + ix + "]: índice de osso fora do limite");
                                if (!Finite(w) || w < 0f) errors.Add(prefix + ".boneWeights[" + ix + "]: peso negativo ou não finito");
                                else sum += w;
                            }
                            if (!Finite(sum) || Math.Abs(sum - 1f) > 0.02f) errors.Add(prefix + ".boneWeights: pesos do vértice " + v + " não somam 1");
                            if (errors.Count > 250) break;
                        }
                    }
                    if (m.blendshapes != null)
                    {
                        var shapeNames = new HashSet<string>(StringComparer.Ordinal);
                        for (int si = 0; si < m.blendshapes.Length; si++)
                        {
                            var sh = m.blendshapes[si];
                            string sp = prefix + ".blendshapes[" + si + "]";
                            if (sh == null) { errors.Add(sp + ": registro nulo"); continue; }
                            if (!SafeShapeName(sh.name)) errors.Add(sp + ".name: nome inválido");
                            else if (!shapeNames.Add(sh.name)) errors.Add(sp + ".name: nome duplicado");
                            int count = sh.indices == null ? 0 : sh.indices.Length;
                            if (sh.deltas == null || sh.deltas.Length != count * 3) errors.Add(sp + ".deltas: tamanho deve ser indices * 3");
                            else CheckFinite(sh.deltas, sp + ".deltas", errors);
                            if (sh.indices != null)
                            {
                                var seen = new HashSet<int>();
                                for (int k = 0; k < sh.indices.Length; k++)
                                {
                                    int ix = sh.indices[k];
                                    if (ix < 0 || ix >= vc) errors.Add(sp + ".indices[" + k + "]: vértice fora do limite");
                                    else if (!seen.Add(ix)) errors.Add(sp + ".indices[" + k + "]: índice duplicado");
                                }
                            }
                        }
                    }
                    if (errors.Count > 250) break;
                }
                if (totalVertices > 1000000) errors.Add("meshes: total de vértices excede 1.000.000");
            }

            if (errors.Count > 0)
            {
                if (errors.Count > 250) errors.RemoveRange(250, errors.Count - 250);
                throw new InvalidDataException("Validação do avatar falhou:\n - " + string.Join("\n - ", errors.ToArray()));
            }
        }

        static void CheckVector(float[] values, int expected, string path, List<string> errors)
        {
            if (values == null || values.Length != expected) { errors.Add(path + ": esperado array com " + expected + " valores"); return; }
            CheckFinite(values, path, errors);
        }

        static void CheckFinite(float[] values, string path, List<string> errors)
        {
            for (int i = 0; i < values.Length; i++)
                if (!Finite(values[i])) { errors.Add(path + "[" + i + "]: valor NaN/infinito"); return; }
        }

        static bool SafeTextureName(string name)
        {
            return !string.IsNullOrEmpty(name) && name == Path.GetFileName(name) &&
                name.IndexOf('/') < 0 && name.IndexOf('\\') < 0 && name.IndexOf(':') < 0 &&
                name.IndexOf("..", StringComparison.Ordinal) < 0 &&
                string.Equals(Path.GetExtension(name), ".png", StringComparison.OrdinalIgnoreCase);
        }

        public static void ValidatePackageFiles(string jsonPath, VASAvatarData data)
        {
            ValidateAvatarData(data);
            ReadAndValidatePalette(jsonPath, data.paletteTexture);
        }

        static byte[] ReadAndValidatePalette(string jsonPath, string paletteName)
        {
            if (!SafeTextureName(paletteName)) throw new InvalidDataException("paletteTexture contém um caminho não permitido.");
            string sourceDir = Path.GetFullPath(Path.GetDirectoryName(jsonPath));
            string candidate = Path.GetFullPath(Path.Combine(sourceDir, paletteName));
            string prefix = sourceDir.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar) + Path.DirectorySeparatorChar;
            if (!candidate.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("O caminho da textura sai da pasta de origem.");
            if (!File.Exists(candidate)) throw new FileNotFoundException("Textura da paleta não encontrada ao lado do JSON.", candidate);
            if ((File.GetAttributes(candidate) & FileAttributes.ReparsePoint) != 0)
                throw new InvalidDataException("A textura da paleta não pode ser um link simbólico/reparse point.");
            var fi = new FileInfo(candidate);
            if (fi.Length < 24 || fi.Length > MaxTextureBytes) throw new InvalidDataException("PNG da paleta vazio ou maior que 16 MB.");
            byte[] bytes = File.ReadAllBytes(candidate);
            byte[] sig = { 137, 80, 78, 71, 13, 10, 26, 10 };
            for (int i = 0; i < sig.Length; i++) if (bytes[i] != sig[i]) throw new InvalidDataException("A textura da paleta não possui assinatura PNG válida.");
            if (bytes[12] != 73 || bytes[13] != 72 || bytes[14] != 68 || bytes[15] != 82)
                throw new InvalidDataException("Cabeçalho IHDR do PNG inválido.");
            uint width = ReadUInt32(bytes, 16), height = ReadUInt32(bytes, 20);
            if (width == 0 || height == 0 || width > 4096 || height > 4096)
                throw new InvalidDataException("Dimensões do PNG fora do limite de 1 a 4096 px.");
            return bytes;
        }

        static uint ReadUInt32(byte[] data, int offset)
        {
            return ((uint)data[offset] << 24) | ((uint)data[offset + 1] << 16) | ((uint)data[offset + 2] << 8) | data[offset + 3];
        }

        public static string Sanitize(string s)
        {
            var r = Regex.Replace(s ?? "", @"[^A-Za-z0-9_\-]", "");
            return string.IsNullOrEmpty(r) ? "Avatar" : r;
        }

        public static string AssetFolder(VASAvatarData data) { return DefaultRoot + "/" + Sanitize(data.name); }

        public static string AssetFolderFor(GameObject root, VASAvatarData data)
        {
            string folder;
            if (root != null && ImportedFolders.TryGetValue(root.GetInstanceID(), out folder)) return folder;
            return AssetFolder(data);
        }

        public static void RememberAssetFolder(GameObject root, string jsonPath, VASAvatarData data)
        {
            if (root == null) return;
            string folder = AssetFolder(data);
            try
            {
                string projectRoot = Path.GetFullPath(Directory.GetParent(Application.dataPath).FullName);
                string fullJson = Path.GetFullPath(jsonPath);
                string prefix = projectRoot.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar) + Path.DirectorySeparatorChar;
                if (fullJson.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
                {
                    string relative = fullJson.Substring(prefix.Length).Replace('\\', '/');
                    if (relative.StartsWith("Assets/", StringComparison.OrdinalIgnoreCase))
                        folder = relative.Substring(0, relative.LastIndexOf('/'));
                }
            }
            catch (Exception) { /* usa o caminho padrão derivado do nome */ }
            ImportedFolders[root.GetInstanceID()] = folder;
        }

        static void EnsureFolder(string path)
        {
            path = path.Replace('\\', '/').TrimEnd('/');
            if (AssetDatabase.IsValidFolder(path)) return;
            int slash = path.LastIndexOf('/');
            if (slash <= 0) throw new IOException("Não foi possível criar a pasta Unity: " + path);
            string parent = path.Substring(0, slash), leaf = path.Substring(slash + 1);
            EnsureFolder(parent);
            string guid = AssetDatabase.CreateFolder(parent, leaf);
            if (string.IsNullOrEmpty(guid) && !AssetDatabase.IsValidFolder(path)) throw new IOException("Falha ao criar pasta Unity: " + path);
        }

        static string UniqueFolder(string baseFolder)
        {
            if (!AssetDatabase.IsValidFolder(baseFolder)) return baseFolder;
            for (int i = 1; i < 10000; i++)
            {
                string candidate = baseFolder + "_Copy_" + i.ToString("00");
                if (!AssetDatabase.IsValidFolder(candidate) && !File.Exists(ToFullPath(candidate))) return candidate;
            }
            throw new IOException("Não foi possível encontrar um nome livre para a cópia do avatar.");
        }

        static string ResolveFolder(string baseFolder, out string backupFolder)
        {
            backupFolder = null;
            EnsureFolder(DefaultRoot);
            if (!AssetDatabase.IsValidFolder(baseFolder)) return baseFolder;
            int choice = EditorUtility.DisplayDialogComplex(
                "Avatar já existe",
                "Já existe uma pasta para este avatar. Escolha como continuar.\n\nSubstituir move a versão atual para Backups antes de importar.",
                "Substituir + backup", "Cancelar", "Criar cópia");
            if (choice == 1) throw new OperationCanceledException("Importação cancelada; nenhum arquivo foi alterado.");
            if (choice == 2) return UniqueFolder(baseFolder);

            string backups = DefaultRoot + "/Backups";
            EnsureFolder(backups);
            string stamp = DateTime.UtcNow.ToString("yyyyMMdd_HHmmss");
            backupFolder = backups + "/" + Path.GetFileName(baseFolder) + "_" + stamp;
            for (int i = 1; AssetDatabase.IsValidFolder(backupFolder); i++) backupFolder = backups + "/" + Path.GetFileName(baseFolder) + "_" + stamp + "_" + i;
            string error = AssetDatabase.MoveAsset(baseFolder, backupFolder);
            if (!string.IsNullOrEmpty(error)) throw new IOException("Não foi possível preservar a versão anterior: " + error);
            return baseFolder;
        }

        static string ToFullPath(string assetPath)
        {
            return Path.Combine(Directory.GetParent(Application.dataPath).FullName, assetPath.Replace('/', Path.DirectorySeparatorChar));
        }

        static string CreateAssetSafely<T>(T obj, string path, List<string> log) where T : UnityEngine.Object
        {
            string finalPath = path;
            if (AssetDatabase.LoadAssetAtPath<UnityEngine.Object>(finalPath) != null)
            {
                finalPath = AssetDatabase.GenerateUniqueAssetPath(path);
                log.Add("AVISO: asset existente preservado; novo arquivo criado em " + finalPath);
            }
            AssetDatabase.CreateAsset(obj, finalPath);
            var loaded = AssetDatabase.LoadAssetAtPath<T>(finalPath);
            if (loaded == null) throw new IOException("Unity não conseguiu criar o asset: " + finalPath);
            return finalPath;
        }

        /// <summary>Cria o avatar na cena. Em falha, remove apenas os arquivos desta operação e restaura backup.</summary>
        public static GameObject Import(string jsonPath, List<string> log)
        {
            var data = Load(jsonPath); // valida JSON inteiro antes de alterar o projeto.
            byte[] jsonBytes = File.ReadAllBytes(jsonPath);
            byte[] paletteBytes = ReadAndValidatePalette(jsonPath, data.paletteTexture); // lê antes de mover uma pasta eventualmente existente.
            string name = Sanitize(data.name);
            string originalFolder = AssetFolder(data);
            string backupFolder = null;
            string folder = null;
            GameObject root = null;

            try
            {
                folder = ResolveFolder(originalFolder, out backupFolder);
                EnsureFolder(folder);
                string projectRoot = Directory.GetParent(Application.dataPath).FullName;

                string jsonDst = folder + "/" + name + ".vrcavatar.json";
                File.WriteAllBytes(Path.Combine(projectRoot, jsonDst), jsonBytes);
                string texDst = folder + "/" + data.paletteTexture; // preserva exatamente o nome referenciado pelo JSON (inclusive Unicode).
                File.WriteAllBytes(Path.Combine(projectRoot, texDst), paletteBytes);
                AssetDatabase.ImportAsset(texDst, ImportAssetOptions.ForceUpdate);
                var ti = AssetImporter.GetAtPath(texDst) as TextureImporter;
                if (ti == null) throw new InvalidDataException("Unity não reconheceu o arquivo PNG importado.");
                ti.filterMode = FilterMode.Point;
                ti.mipmapEnabled = false;
                ti.wrapMode = TextureWrapMode.Clamp;
                ti.textureCompression = TextureImporterCompression.Uncompressed;
                ti.SaveAndReimport();
                var tex = AssetDatabase.LoadAssetAtPath<Texture2D>(texDst);
                if (tex == null) throw new InvalidDataException("Unity não conseguiu carregar a textura da paleta.");

                // material
                var shader = Shader.Find("VRChat/Mobile/Toon Lit");
                if (shader == null) shader = Shader.Find("Standard");
                if (shader == null) throw new InvalidOperationException("Nenhum shader compatível foi encontrado (Toon Lit/Standard).");
                var mat = new Material(shader) { name = name + "_Palette", mainTexture = tex };
                if (mat.HasProperty("_Glossiness")) mat.SetFloat("_Glossiness", 0f);
                CreateAssetSafely(mat, folder + "/" + name + "_Palette.mat", log);

                // hierarquia
                root = new GameObject(name);
                Undo.RegisterCreatedObjectUndo(root, "Importar avatar");
                var armature = new GameObject("Armature");
                armature.transform.SetParent(root.transform, false);
                var bones = new Transform[data.bones.Length];
                for (int i = 0; i < bones.Length; i++)
                {
                    var b = data.bones[i];
                    var go = new GameObject(b.name);
                    go.transform.SetParent(b.parent >= 0 ? bones[b.parent] : armature.transform, false);
                    go.transform.position = new Vector3(b.position[0], b.position[1], b.position[2]);
                    bones[i] = go.transform;
                }
                var bind = new Matrix4x4[bones.Length];
                for (int i = 0; i < bones.Length; i++)
                    bind[i] = bones[i].worldToLocalMatrix * root.transform.localToWorldMatrix;

                Transform hips = FindBone(bones, data, "Hips");
                if (hips == null) throw new InvalidDataException("Humanoid não contém o osso Hips.");

                // malhas
                foreach (var m in data.meshes)
                {
                    var mesh = BuildMesh(m, bind, name);
                    string meshPath = CreateAssetSafely(mesh, folder + "/" + name + "_" + m.name + ".asset", log);
                    mesh = AssetDatabase.LoadAssetAtPath<Mesh>(meshPath);
                    var go = new GameObject(m.name);
                    go.transform.SetParent(root.transform, false);
                    var smr = go.AddComponent<SkinnedMeshRenderer>();
                    smr.sharedMesh = mesh;
                    smr.bones = bones;
                    smr.rootBone = hips;
                    smr.sharedMaterial = mat;
                    smr.localBounds = mesh.bounds;
                    smr.updateWhenOffscreen = false;
                }

                // Humanoid: uma falha de validação é impeditiva; nunca continuar com Animator vazio.
                var animator = root.AddComponent<Animator>();
                var avatar = BuildHumanoid(root, data, folder + "/" + name + "_Avatar.asset", log);
                if (avatar == null || !avatar.isValid || !avatar.isHuman)
                    throw new InvalidDataException("O Unity não validou o Humanoid; a importação foi revertida. Confira os mapeamentos no JSON e a hierarquia dos ossos.");
                animator.avatar = avatar;

                AssetDatabase.SaveAssets();
                ImportedFolders[root.GetInstanceID()] = folder;
                log.Add("Avatar '" + name + "' importado: " + data.meshes.Length + " malha(s), " + bones.Length + " ossos. Arquivos em " + folder);
                log.Add("Versão anterior preservada em: " + (backupFolder ?? "nenhuma"));
                Selection.activeGameObject = root;
                return root;
            }
            catch
            {
                if (root != null) Undo.DestroyObjectImmediate(root);
                bool removedNewFolder = true;
                if (!string.IsNullOrEmpty(folder) && AssetDatabase.IsValidFolder(folder))
                {
                    removedNewFolder = AssetDatabase.DeleteAsset(folder) && !AssetDatabase.IsValidFolder(folder);
                    if (!removedNewFolder) log.Add("ERRO: não foi possível limpar completamente a pasta da importação com falha: " + folder);
                }
                if (!string.IsNullOrEmpty(backupFolder) && AssetDatabase.IsValidFolder(backupFolder) && !AssetDatabase.IsValidFolder(originalFolder))
                {
                    string restoreError = AssetDatabase.MoveAsset(backupFolder, originalFolder);
                    if (!string.IsNullOrEmpty(restoreError)) log.Add("ERRO ao restaurar backup " + backupFolder + ": " + restoreError);
                }
                else if (!string.IsNullOrEmpty(backupFolder) && AssetDatabase.IsValidFolder(backupFolder) && !removedNewFolder)
                {
                    log.Add("Backup preservado sem alteração em " + backupFolder + ". Restauração manual necessária porque a pasta nova não pôde ser removida.");
                }
                AssetDatabase.Refresh();
                throw;
            }
        }

        static Transform FindBone(Transform[] bones, VASAvatarData data, string name)
        {
            for (int i = 0; i < data.bones.Length; i++) if (data.bones[i].name == name) return bones[i];
            return null;
        }

        static Mesh BuildMesh(VASMesh m, Matrix4x4[] bind, string avatarName)
        {
            var mesh = new Mesh { name = avatarName + "_" + m.name };
            int vc = m.positions.Length / 3;
            if (vc > 65535) mesh.indexFormat = IndexFormat.UInt32;
            mesh.vertices = V3(m.positions);
            mesh.normals = V3(m.normals);
            mesh.uv = V2(m.uv);
            mesh.triangles = m.triangles;
            var bw = new BoneWeight[vc];
            for (int v = 0; v < vc; v++)
            {
                int o = v * 4;
                bw[v].boneIndex0 = m.boneIndices[o]; bw[v].weight0 = m.boneWeights[o];
                bw[v].boneIndex1 = m.boneIndices[o + 1]; bw[v].weight1 = m.boneWeights[o + 1];
                bw[v].boneIndex2 = m.boneIndices[o + 2]; bw[v].weight2 = m.boneWeights[o + 2];
                bw[v].boneIndex3 = m.boneIndices[o + 3]; bw[v].weight3 = m.boneWeights[o + 3];
            }
            mesh.boneWeights = bw;
            mesh.bindposes = bind;
            if (m.blendshapes != null)
            {
                foreach (var s in m.blendshapes)
                {
                    var dv = new Vector3[vc];
                    if (s.indices != null)
                        for (int k = 0; k < s.indices.Length; k++)
                            dv[s.indices[k]] = new Vector3(s.deltas[k * 3], s.deltas[k * 3 + 1], s.deltas[k * 3 + 2]);
                    mesh.AddBlendShapeFrame(s.name, 100f, dv, new Vector3[vc], new Vector3[vc]);
                }
            }
            mesh.RecalculateBounds();
            mesh.RecalculateTangents();
            return mesh;
        }

        static Vector3[] V3(float[] a)
        {
            var v = new Vector3[a.Length / 3];
            for (int i = 0; i < v.Length; i++) v[i] = new Vector3(a[i * 3], a[i * 3 + 1], a[i * 3 + 2]);
            return v;
        }

        static Vector2[] V2(float[] a)
        {
            var v = new Vector2[a.Length / 2];
            for (int i = 0; i < v.Length; i++) v[i] = new Vector2(a[i * 2], a[i * 2 + 1]);
            return v;
        }

        static string UnityHumanName(string h)
        {
            return Regex.Replace(h, "^(Left|Right)(Thumb|Index|Middle|Ring|Little)(Proximal|Intermediate|Distal)$", "$1 $2 $3");
        }

        static UnityEngine.Avatar BuildHumanoid(GameObject root, VASAvatarData data, string assetPath, List<string> log)
        {
            var human = new List<HumanBone>();
            foreach (var h in data.humanoid)
            {
                human.Add(new HumanBone
                {
                    humanName = UnityHumanName(h.human),
                    boneName = h.bone,
                    limit = new HumanLimit { useDefaultValues = true }
                });
            }
            var skeleton = new List<SkeletonBone>();
            foreach (var t in root.GetComponentsInChildren<Transform>(true))
            {
                skeleton.Add(new SkeletonBone
                {
                    name = t.name,
                    position = t.localPosition,
                    rotation = t.localRotation,
                    scale = t.localScale
                });
            }
            var desc = new HumanDescription
            {
                human = human.ToArray(),
                skeleton = skeleton.ToArray(),
                upperArmTwist = 0.5f,
                lowerArmTwist = 0.5f,
                upperLegTwist = 0.5f,
                lowerLegTwist = 0.5f,
                armStretch = 0.05f,
                legStretch = 0.05f,
                feetSpacing = 0f,
                hasTranslationDoF = false
            };
            var avatar = UnityEngine.AvatarBuilder.BuildHumanAvatar(root, desc);
            if (avatar == null || !avatar.isValid || !avatar.isHuman)
            {
                log.Add("ERRO: Unity BuildHumanAvatar retornou um Avatar inválido/não humanoide. A operação será desfeita.");
                if (avatar != null) UnityEngine.Object.DestroyImmediate(avatar);
                return null;
            }
            avatar.name = Sanitize(data.name) + "_Avatar";
            string createdPath = CreateAssetSafely(avatar, assetPath, log);
            return AssetDatabase.LoadAssetAtPath<UnityEngine.Avatar>(createdPath);
        }
    }
}
