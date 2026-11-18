// VRChat Avatar Studio - janela e menus do Unity
using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;

namespace VRChatAvatarStudio.EditorTools
{
    public class VASWindow : EditorWindow
    {
        string jsonPath = "";
        readonly VASSetupOptions opt = new VASSetupOptions();
        readonly List<string> log = new List<string>();
        Vector2 scroll;

        [MenuItem("VRChat Avatar Studio/Abrir painel")]
        public static void Open()
        {
            var w = GetWindow<VASWindow>("Avatar Studio");
            w.minSize = new Vector2(380, 420);
        }

        [MenuItem("VRChat Avatar Studio/Validar arquivo .vrcavatar.json...")]
        public static void MenuValidate()
        {
            var path = EditorUtility.OpenFilePanel("Escolha o arquivo .vrcavatar.json", "", "json");
            if (string.IsNullOrEmpty(path)) return;
            var l = new List<string>();
            Guard(l, () =>
            {
                var data = VASImporter.Load(path);
                VASImporter.ValidatePackageFiles(path, data);
                l.Add("VALIDAÇÃO LOCAL APROVADA: JSON e PNG estruturalmente válidos.");
                l.Add("Malhas: " + data.meshes.Length + " · ossos: " + data.bones.Length + " · PhysBones: " + (data.physbones == null ? 0 : data.physbones.Length));
                l.Add("Esta verificação não compila C# nem substitui a validação do SDK no Unity.");
            });
            Report(l);
        }

        [MenuItem("VRChat Avatar Studio/Importar e configurar tudo...")]
        public static void MenuAll()
        {
            var path = EditorUtility.OpenFilePanel("Escolha o arquivo .vrcavatar.json", "", "json");
            if (string.IsNullOrEmpty(path)) return;
            var l = new List<string>();
            Guard(l, () => { var go = VASImporter.Import(path, l); VASVRChatSetup.Run(go, VASImporter.Load(path), new VASSetupOptions(), l); VASPerformanceCheck.Run(go, l); });
            Report(l);
        }

        [MenuItem("VRChat Avatar Studio/Configurar avatar selecionado para o VRChat")]
        public static void MenuConfigure()
        {
            var l = new List<string>();
            Guard(l, () => ConfigureSelected(new VASSetupOptions(), l));
            Report(l);
        }

        [MenuItem("VRChat Avatar Studio/Verificar desempenho do avatar selecionado")]
        public static void MenuPerf()
        {
            var l = new List<string>();
            Guard(l, () =>
            {
                var go = Selection.activeGameObject;
                if (go == null) throw new InvalidOperationException("Selecione o avatar na Hierarchy.");
                VASPerformanceCheck.Run(go.transform.root.gameObject, l);
            });
            Report(l);
        }

        static void Report(List<string> l)
        {
            var text = string.Join("\n", l.ToArray());
            Debug.Log("[VRChat Avatar Studio]\n" + text);
            var w = GetWindow<VASWindow>("Avatar Studio");
            w.log.Clear(); w.log.AddRange(l); w.Repaint();
        }

        static void Guard(List<string> l, Action a)
        {
            try { a(); }
            catch (Exception e) { l.Add("ERRO: " + e.Message); Debug.LogException(e); }
        }

        static void ConfigureSelected(VASSetupOptions o, List<string> l)
        {
            var go = Selection.activeGameObject;
            if (go == null) throw new InvalidOperationException("Selecione o avatar (objeto raiz) na Hierarchy.");
            go = go.transform.root.gameObject;
            string path = FindJson(go.name);
            if (path == null)
            {
                path = EditorUtility.OpenFilePanel("Nao achei o .vrcavatar.json deste avatar - escolha-o", "", "json");
                if (string.IsNullOrEmpty(path)) throw new InvalidOperationException("Operacao cancelada.");
            }
            var data = VASImporter.Load(path);
            VASImporter.RememberAssetFolder(go, path, data);
            VASVRChatSetup.Run(go, data, o, l);
        }

        static string FindJson(string avatarName)
        {
            var guids = AssetDatabase.FindAssets(avatarName + ".vrcavatar");
            foreach (var g in guids)
            {
                var p = AssetDatabase.GUIDToAssetPath(g);
                if (p.EndsWith(".vrcavatar.json", StringComparison.OrdinalIgnoreCase))
                    return Path.Combine(Directory.GetParent(Application.dataPath).FullName, p);
            }
            return null;
        }

        void OnGUI()
        {
            EditorGUILayout.Space();
            EditorGUILayout.LabelField("VRChat Avatar Studio", EditorStyles.boldLabel);
            EditorGUILayout.HelpBox("1) Exporte o pacote no Studio.  2) Valide o JSON/PNG.  3) Importe e configure.  4) Revise o avatar e valide/publice pelo VRChat SDK > Show Control Panel.", MessageType.Info);

            EditorGUILayout.BeginHorizontal();
            jsonPath = EditorGUILayout.TextField("Arquivo .vrcavatar.json", jsonPath);
            if (GUILayout.Button("...", GUILayout.Width(30)))
            {
                var p = EditorUtility.OpenFilePanel("Escolha o arquivo .vrcavatar.json", "", "json");
                if (!string.IsNullOrEmpty(p)) jsonPath = p;
            }
            EditorGUILayout.EndHorizontal();

            EditorGUILayout.Space();
            EditorGUILayout.LabelField("Configuracao do VRChat", EditorStyles.boldLabel);
            opt.descriptor = EditorGUILayout.ToggleLeft("Avatar Descriptor (posicao da camera / View Position)", opt.descriptor);
            opt.visemes = EditorGUILayout.ToggleLeft("Visemas (15 blendshapes de fala)", opt.visemes);
            opt.eyes = EditorGUILayout.ToggleLeft("Olhos: seguir olhar + piscar", opt.eyes);
            opt.physBones = EditorGUILayout.ToggleLeft("PhysBones (cabelo, orelhas, cauda, acessorios)", opt.physBones);
            opt.expressions = EditorGUILayout.ToggleLeft("Menu: emocoes + liga/desliga roupas e acessorios", opt.expressions);

            EditorGUILayout.Space();
            using (new EditorGUI.DisabledScope(string.IsNullOrEmpty(jsonPath) || !File.Exists(jsonPath)))
            {
                if (GUILayout.Button("Validar JSON e PNG (sem importar)"))
                {
                    var l = new List<string>();
                    Guard(l, () =>
                    {
                        var data = VASImporter.Load(jsonPath);
                        VASImporter.ValidatePackageFiles(jsonPath, data);
                        l.Add("VALIDAÇÃO LOCAL APROVADA: " + data.meshes.Length + " malha(s), " + data.bones.Length + " osso(s).");
                        l.Add("Confirme Humanoid, Descriptor, expressões e Build & Publish dentro do Unity com o SDK instalado.");
                    });
                    Report(l);
                }
                if (GUILayout.Button("Importar e configurar tudo", GUILayout.Height(30)))
                {
                    var l = new List<string>();
                    Guard(l, () => { var go = VASImporter.Import(jsonPath, l); VASVRChatSetup.Run(go, VASImporter.Load(jsonPath), opt, l); VASPerformanceCheck.Run(go, l); });
                    Report(l);
                }
                if (GUILayout.Button("So importar (sem configurar o VRChat)"))
                {
                    var l = new List<string>();
                    Guard(l, () => VASImporter.Import(jsonPath, l));
                    Report(l);
                }
            }
            if (GUILayout.Button("Configurar o avatar selecionado"))
            {
                var l = new List<string>();
                Guard(l, () => ConfigureSelected(opt, l));
                Report(l);
            }
            if (GUILayout.Button("Verificar desempenho do avatar selecionado")) MenuPerf();

            EditorGUILayout.Space();
            EditorGUILayout.LabelField("Resultado", EditorStyles.boldLabel);
            scroll = EditorGUILayout.BeginScrollView(scroll, GUILayout.ExpandHeight(true));
            foreach (var line in log) EditorGUILayout.LabelField(line, EditorStyles.wordWrappedLabel);
            EditorGUILayout.EndScrollView();
        }
    }
}
