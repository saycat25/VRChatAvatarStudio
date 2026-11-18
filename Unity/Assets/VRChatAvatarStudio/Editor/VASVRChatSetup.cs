// VRChat Avatar Studio - configura o avatar para o VRChat SDK3 (Avatars).
// Usa reflexao + SerializedObject: compila mesmo sem o SDK instalado e tolera mudancas de versao do SDK.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.RegularExpressions;
using UnityEditor;
using UnityEditor.Animations;
using UnityEngine;

namespace VRChatAvatarStudio.EditorTools
{
    public class VASSetupOptions
    {
        public bool descriptor = true;
        public bool visemes = true;
        public bool eyes = true;
        public bool physBones = true;
        public bool expressions = true;   // controlador FX + parametros + menu (emocoes e liga/desliga de roupas/acessorios)
    }

    public static class VASVRChatSetup
    {
        static readonly string[] VisemeOrder =
        {
            "vrc.v_sil", "vrc.v_pp", "vrc.v_ff", "vrc.v_th", "vrc.v_dd", "vrc.v_kk", "vrc.v_ch", "vrc.v_ss",
            "vrc.v_nn", "vrc.v_rr", "vrc.v_aa", "vrc.v_e", "vrc.v_ih", "vrc.v_oh", "vrc.v_ou"
        };

        // emocoes: (nome no menu, blendshape)
        static readonly string[][] Emotions =
        {
            new[] { "Sorriso", "Smile" }, new[] { "Bravo", "Angry" }, new[] { "Triste", "Sad" },
            new[] { "Surpresa", "Surprised" }, new[] { "Rubor", "Blush" }
        };

        public static Type FindType(string fullName)
        {
            foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
            {
                Type t = null;
                try { t = asm.GetType(fullName, false); } catch (Exception) { /* assembly problematico */ }
                if (t != null) return t;
            }
            return null;
        }

        // ---------------------------------------------------------------- helpers de SerializedProperty

        static SerializedProperty Prop(SerializedObject so, string path, List<string> log)
        {
            var p = so.FindProperty(path);
            if (p == null) log.Add("AVISO: campo '" + path + "' nao existe nesta versao do SDK - configure manualmente.");
            return p;
        }

        static string Norm(string s) { return (s ?? "").Replace(" ", "").ToLowerInvariant(); }

        static bool SetEnum(SerializedProperty p, string name)
        {
            if (p == null) return false;
            var names = p.enumNames;
            for (int i = 0; i < names.Length; i++)
                if (Norm(names[i]) == Norm(name)) { p.enumValueIndex = i; return true; }
            return false;
        }

        static Transform Find(Transform root, string name)
        {
            foreach (var t in root.GetComponentsInChildren<Transform>(true)) if (t.name == name) return t;
            return null;
        }

        static SkinnedMeshRenderer Smr(GameObject root, string meshName)
        {
            var t = root.transform.Find(meshName);
            return t != null ? t.GetComponent<SkinnedMeshRenderer>() : null;
        }

        static int ShapeIndex(SkinnedMeshRenderer smr, string name)
        {
            return smr == null || smr.sharedMesh == null ? -1 : smr.sharedMesh.GetBlendShapeIndex(name);
        }

        // ---------------------------------------------------------------- execucao

        public static void Run(GameObject root, VASAvatarData data, VASSetupOptions opt, List<string> log)
        {
            string name = VASImporter.Sanitize(data.name);
            string folder = VASImporter.AssetFolderFor(root, data);
            var body = Smr(root, "Body");

            var tDesc = FindType("VRC.SDK3.Avatars.Components.VRCAvatarDescriptor");
            if (tDesc == null)
            {
                log.Add("ERRO: VRChat SDK (Avatars 3.0) nao encontrado neste projeto. Instale-o pelo VRChat Creator Companion e rode de novo.");
                return;
            }

            Component desc = null;
            SerializedObject so = null;
            if (opt.descriptor || opt.visemes || opt.eyes || opt.expressions)
            {
                desc = root.GetComponent(tDesc);
                if (desc == null) desc = Undo.AddComponent(root, tDesc);
                so = new SerializedObject(desc);
            }

            if (so != null && opt.descriptor)
            {
                var vp = Prop(so, "ViewPosition", log);
                if (vp != null) vp.vector3Value = new Vector3(data.viewPosition[0], data.viewPosition[1], data.viewPosition[2]);
                log.Add("Descriptor: ViewPosition definido (" + data.viewPosition[0].ToString("0.###") + ", " +
                    data.viewPosition[1].ToString("0.###") + ", " + data.viewPosition[2].ToString("0.###") + ").");
            }

            if (so != null && opt.visemes && body != null)
            {
                var ls = Prop(so, "lipSync", log);
                if (ls != null && !SetEnum(ls, "VisemeBlendShape")) ls.enumValueIndex = 3;
                var sm = Prop(so, "VisemeSkinnedMesh", log);
                if (sm != null) sm.objectReferenceValue = body;
                var arr = Prop(so, "VisemeBlendShapes", log);
                if (arr != null)
                {
                    arr.arraySize = VisemeOrder.Length;
                    for (int i = 0; i < VisemeOrder.Length; i++)
                        arr.GetArrayElementAtIndex(i).stringValue = ShapeIndex(body, VisemeOrder[i]) >= 0 ? VisemeOrder[i] : "";
                }
                log.Add("Visemas: 15 blendshapes vrc.v_* ligados ao corpo.");
            }

            if (so != null && opt.eyes && body != null)
            {
                var ee = so.FindProperty("enableEyeLook");
                if (ee != null) ee.boolValue = true;
                var l = Prop(so, "customEyeLookSettings.leftEye", log);
                var r = Prop(so, "customEyeLookSettings.rightEye", log);
                if (l != null) l.objectReferenceValue = Find(root.transform, data.eyes.left);
                if (r != null) r.objectReferenceValue = Find(root.transform, data.eyes.right);
                var et = Prop(so, "customEyeLookSettings.eyelidType", log);
                if (et != null && !SetEnum(et, "Blendshapes")) et.enumValueIndex = 2;
                var es = Prop(so, "customEyeLookSettings.eyelidsSkinnedMesh", log);
                if (es != null) es.objectReferenceValue = body;
                var eb = Prop(so, "customEyeLookSettings.eyelidsBlendshapes", log);
                if (eb != null)
                {
                    eb.arraySize = 3;   // piscar, olhar para cima, olhar para baixo
                    eb.GetArrayElementAtIndex(0).intValue = ShapeIndex(body, "Blink");
                    eb.GetArrayElementAtIndex(1).intValue = ShapeIndex(body, "LookUp");
                    eb.GetArrayElementAtIndex(2).intValue = ShapeIndex(body, "LookDown");
                }
                log.Add("Olhos: seguir olhar e piscar configurados (blendshapes Blink/LookUp/LookDown).");
            }

            if (opt.physBones) AddPhysBones(root, data, log);

            if (so != null && opt.expressions) BuildExpressions(root, data, so, folder, name, log);

            if (so != null) so.ApplyModifiedProperties();
            if (desc != null) EditorUtility.SetDirty(desc);
            log.Add("Configuracao do VRChat concluida. Abra VRChat SDK > Show Control Panel para validar e publicar.");
        }

        // ---------------------------------------------------------------- PhysBones

        static void AddPhysBones(GameObject root, VASAvatarData data, List<string> log)
        {
            var tPb = FindType("VRC.SDK3.Dynamics.PhysBone.Components.VRCPhysBone");
            if (tPb == null)
            {
                log.Add("AVISO: PhysBones nao encontrados no SDK (versao antiga?). Pulei os PhysBones.");
                return;
            }
            int n = 0;
            foreach (var pb in data.physbones ?? new VASPhysBone[0])
            {
                var t = Find(root.transform, pb.root);
                if (t == null) continue;
                var comp = t.GetComponent(tPb);
                if (comp == null) comp = Undo.AddComponent(t.gameObject, tPb);
                var so = new SerializedObject(comp);
                float pull = 0.2f, spring = 0.25f, immobile = 0.1f, gravity = 0.0f;
                switch (pb.kind)
                {
                    case "hair": pull = 0.2f; spring = 0.3f; immobile = 0.15f; gravity = 0.05f; break;
                    case "tail": pull = 0.15f; spring = 0.25f; immobile = 0.05f; gravity = 0.05f; break;
                    case "ear": pull = 0.35f; spring = 0.35f; immobile = 0.2f; break;
                    case "accessory": pull = 0.25f; spring = 0.3f; immobile = 0.1f; gravity = 0.1f; break;
                }
                var tmp = new List<string>();   // campos opcionais: sem aviso individual
                SetObj(so, "rootTransform", t, tmp);
                if (pb.endpoint != null && pb.endpoint.Length == 3)
                {
                    var ep = so.FindProperty("endpointPosition");
                    if (ep != null) ep.vector3Value = new Vector3(pb.endpoint[0], pb.endpoint[1], pb.endpoint[2]);
                }
                SetFloat(so, "pull", pull);
                SetFloat(so, "spring", spring);
                SetFloat(so, "immobile", immobile);
                SetFloat(so, "gravity", gravity);
                SetFloat(so, "radius", 0.0f);
                so.ApplyModifiedProperties();
                n++;
            }
            log.Add("PhysBones: " + n + " componente(s) adicionados (cabelo, orelhas, cauda e acessorios que balancam).");
        }

        static void SetFloat(SerializedObject so, string path, float v)
        {
            var p = so.FindProperty(path);
            if (p != null && p.propertyType == SerializedPropertyType.Float) p.floatValue = v;
        }

        static void SetObj(SerializedObject so, string path, UnityEngine.Object o, List<string> log)
        {
            var p = Prop(so, path, log);
            if (p != null) p.objectReferenceValue = o;
        }

        // ---------------------------------------------------------------- Expressoes (FX + parametros + menu)

        static void BuildExpressions(GameObject root, VASAvatarData data, SerializedObject descSo, string folder, string name, List<string> log)
        {
            var tParams = FindType("VRC.SDK3.Avatars.ScriptableObjects.VRCExpressionParameters");
            var tMenu = FindType("VRC.SDK3.Avatars.ScriptableObjects.VRCExpressionsMenu");
            if (tParams == null || tMenu == null)
            {
                log.Add("AVISO: classes de menu/parametros do SDK nao encontradas. Pulei o menu de expressoes.");
                return;
            }
            var body = Smr(root, "Body");
            var emotions = Emotions.Where(e => ShapeIndex(body, e[1]) >= 0).ToArray();
            var candidates = data.meshes.Where(m => m.toggle).ToList();
            int expressionBits = emotions.Length > 0 ? 8 : 0; // parametro Int
            int maxToggles = Math.Min(64, Math.Max(0, 256 - expressionBits));
            var toggles = candidates.Take(maxToggles).ToList();
            var omitted = candidates.Skip(maxToggles).Select(m => m.label ?? m.name).ToArray();
            var toggleParams = new Dictionary<string, string>(StringComparer.Ordinal);
            var usedParameters = new HashSet<string>(StringComparer.Ordinal);
            foreach (var m in toggles)
            {
                string raw = "T_" + Regex.Replace(m.name ?? "Item", @"[^A-Za-z0-9_]", "");
                if (raw.Length > 30) raw = raw.Substring(0, 30);
                string param = raw;
                int suffix = 2;
                while (!usedParameters.Add(param))
                {
                    string tail = "_" + suffix++;
                    param = raw.Substring(0, Math.Min(raw.Length, 30 - tail.Length)) + tail;
                }
                toggleParams[m.name] = param;
            }
            if (omitted.Length > 0)
                log.Add("AVISO: limite de segurança local para 64 toggles. Itens não incluídos (não foram descartados silenciosamente): " + string.Join(", ", omitted));

            // ---- controlador FX (o caminho nunca apaga assets já existentes)
            string animDir = folder + "/Anim";
            if (!AssetDatabase.IsValidFolder(animDir)) AssetDatabase.CreateFolder(folder, "Anim");
            string ctrlPath = AssetDatabase.GenerateUniqueAssetPath(folder + "/" + name + "_FX.controller");
            var ctrl = AnimatorController.CreateAnimatorControllerAtPath(ctrlPath);
            if (emotions.Length > 0) ctrl.AddParameter("Expression", AnimatorControllerParameterType.Int);
            foreach (var m in toggles) ctrl.AddParameter(toggleParams[m.name], AnimatorControllerParameterType.Bool);

            // camada das emocoes
            if (emotions.Length > 0)
            {
                var layer = NewLayer(ctrl, "Expressions");
                var sm = layer.stateMachine;
                var neutral = sm.AddState("Neutro", new Vector3(260, 0));
                sm.defaultState = neutral;
                var t0 = sm.AddAnyStateTransition(neutral);
                Configure(t0); t0.AddCondition(AnimatorConditionMode.Equals, 0, "Expression");
                for (int i = 0; i < emotions.Length; i++)
                {
                    var clip = BlendShapeClip(animDir + "/" + name + "_" + emotions[i][1] + ".anim", "Body", emotions[i][1], 100f);
                    var st = sm.AddState(emotions[i][0], new Vector3(260, 60 * (i + 1)));
                    st.motion = clip;
                    var tr = sm.AddAnyStateTransition(st);
                    Configure(tr); tr.AddCondition(AnimatorConditionMode.Equals, i + 1, "Expression");
                }
                ApplyLayer(ctrl, layer);
            }

            // uma camada por objeto que liga/desliga
            foreach (var m in toggles)
            {
                var layer = NewLayer(ctrl, "Toggle " + (m.label ?? m.name));
                var sm = layer.stateMachine;
                var on = sm.AddState("Ligado", new Vector3(260, 0));
                var off = sm.AddState("Desligado", new Vector3(260, 60));
                on.motion = ActiveClip(animDir + "/" + name + "_" + m.name + "_On.anim", m.name, 1f);
                off.motion = ActiveClip(animDir + "/" + name + "_" + m.name + "_Off.anim", m.name, 0f);
                sm.defaultState = on;
                var a = on.AddTransition(off); Configure(a); a.AddCondition(AnimatorConditionMode.IfNot, 0, toggleParams[m.name]);
                var b = off.AddTransition(on); Configure(b); b.AddCondition(AnimatorConditionMode.If, 0, toggleParams[m.name]);
                ApplyLayer(ctrl, layer);
            }
            EditorUtility.SetDirty(ctrl);

            // ---- parametros com orçamento explícito de bits
            string parPath = folder + "/" + name + "_Parameters.asset";
            var pars = ScriptableObject.CreateInstance(tParams);
            pars = ReplaceAsset(pars, parPath);
            var pso = new SerializedObject(pars);
            var plist = pso.FindProperty("parameters");
            if (plist != null)
            {
                var defs = new List<string[]>();
                if (emotions.Length > 0) defs.Add(new[] { "Expression", "Int", "0" });
                foreach (var m in toggles) defs.Add(new[] { toggleParams[m.name], "Bool", "1" });
                plist.arraySize = defs.Count;
                for (int i = 0; i < defs.Count; i++)
                {
                    var el = plist.GetArrayElementAtIndex(i);
                    el.FindPropertyRelative("name").stringValue = defs[i][0];
                    SetEnum(el.FindPropertyRelative("valueType"), defs[i][1]);
                    var dv = el.FindPropertyRelative("defaultValue"); if (dv != null) dv.floatValue = float.Parse(defs[i][2]);
                    var sv = el.FindPropertyRelative("saved"); if (sv != null) sv.boolValue = true;
                    var ns = el.FindPropertyRelative("networkSynced"); if (ns != null) ns.boolValue = true;
                }
                pso.ApplyModifiedProperties();
            }
            else log.Add("AVISO: lista 'parameters' nao encontrada no SDK.");
            EditorUtility.SetDirty(pars);

            // ---- menus: cada nível contém no máximo oito controles.
            var rootMenuCtrls = new List<Action<SerializedProperty>>();
            if (emotions.Length > 0)
            {
                var sub = CreateMenu(tMenu, folder + "/" + name + "_Menu_Expressoes.asset");
                var items = new List<Action<SerializedProperty>> { c => Toggle(c, "Neutro", "Expression", 0) };
                for (int i = 0; i < emotions.Length; i++)
                {
                    int v = i + 1; string nm = emotions[i][0];
                    items.Add(c => Toggle(c, nm, "Expression", v));
                }
                FillMenu(sub, items);
                rootMenuCtrls.Add(c => SubMenu(c, "Expressoes", sub));
            }
            if (toggles.Count > 0)
            {
                int serial = 0;
                var sub = BuildToggleMenuTree(tMenu, folder, name, toggles, toggleParams, ref serial);
                rootMenuCtrls.Add(c => SubMenu(c, toggles.Count > 8 ? "Roupas/Acess. (páginas)" : "Roupas/Acessorios", sub));
            }
            var rootMenu = CreateMenu(tMenu, folder + "/" + name + "_Menu.asset");
            FillMenu(rootMenu, rootMenuCtrls);
            AssetDatabase.SaveAssets();

            // ---- liga ao descriptor
            var cl = descSo.FindProperty("customizeAnimationLayers");
            if (cl != null) cl.boolValue = true;
            var layers = descSo.FindProperty("baseAnimationLayers");
            bool fxSet = false;
            if (layers != null)
            {
                for (int i = 0; i < layers.arraySize && !fxSet; i++)
                {
                    var el = layers.GetArrayElementAtIndex(i);
                    var ty = el.FindPropertyRelative("type");
                    if (ty != null && ty.propertyType == SerializedPropertyType.Enum &&
                        ty.enumValueIndex >= 0 && ty.enumValueIndex < ty.enumNames.Length && ty.enumNames[ty.enumValueIndex] == "FX")
                    {
                        var ac = el.FindPropertyRelative("animatorController"); if (ac != null) ac.objectReferenceValue = ctrl;
                        var ie = el.FindPropertyRelative("isEnabled"); if (ie != null) ie.boolValue = true;
                        var idf = el.FindPropertyRelative("isDefault"); if (idf != null) idf.boolValue = false;
                        fxSet = true;
                    }
                }
            }
            if (!fxSet) log.Add("AVISO: camada FX nao encontrada no descriptor. Arraste o controlador indicado para a camada FX manualmente.");
            var em = descSo.FindProperty("expressionsMenu"); if (em != null) em.objectReferenceValue = rootMenu;
            var ep = descSo.FindProperty("expressionParameters"); if (ep != null) ep.objectReferenceValue = pars;
            log.Add("Expressoes: FX, parâmetros (" + expressionBits + " bits de emoção + " + toggles.Count + " bits de toggle), menu paginado com " + emotions.Length + " emoções e " + toggles.Count + " toggles.");
            log.Add("Observação: o menu respeita 8 controles por página; o limite de 64 toggles é uma proteção local, não uma validação oficial do SDK.");
        }

        static UnityEngine.Object BuildToggleMenuTree(Type tMenu, string folder, string name, List<VASMesh> items,
            Dictionary<string, string> parameters, ref int serial)
        {
            int pageId = ++serial;
            var menu = CreateMenu(tMenu, folder + "/" + name + "_Menu_Toggles_" + pageId + ".asset");
            var controls = new List<Action<SerializedProperty>>();
            if (items.Count <= 8)
            {
                foreach (var m in items)
                {
                    var item = m;
                    controls.Add(c => Toggle(c, item.label ?? item.name, parameters[item.name], 1));
                }
            }
            else
            {
                int chunkSize = (int)Math.Ceiling(items.Count / 8.0);
                int page = 0;
                for (int start = 0; start < items.Count; start += chunkSize)
                {
                    var chunk = items.Skip(start).Take(chunkSize).ToList();
                    var child = BuildToggleMenuTree(tMenu, folder, name, chunk, parameters, ref serial);
                    string label = "Página " + (++page);
                    controls.Add(c => SubMenu(c, label, child));
                }
            }
            FillMenu(menu, controls);
            return menu;
        }

        // ---- animator helpers

        static AnimatorControllerLayer NewLayer(AnimatorController ctrl, string name)
        {
            var layer = new AnimatorControllerLayer
            {
                name = name,
                defaultWeight = 1f,
                stateMachine = new AnimatorStateMachine { name = name, hideFlags = HideFlags.HideInHierarchy }
            };
            AssetDatabase.AddObjectToAsset(layer.stateMachine, ctrl);
            return layer;
        }

        static void ApplyLayer(AnimatorController ctrl, AnimatorControllerLayer layer) { ctrl.AddLayer(layer); }

        static void Configure(AnimatorStateTransition t)
        {
            t.hasExitTime = false;
            t.hasFixedDuration = true;
            t.duration = 0.1f;
            t.canTransitionToSelf = false;
        }

        static AnimationClip BlendShapeClip(string path, string objPath, string shape, float value)
        {
            var clip = new AnimationClip { name = System.IO.Path.GetFileNameWithoutExtension(path) };
            AnimationUtility.SetEditorCurve(clip,
                EditorCurveBinding.FloatCurve(objPath, typeof(SkinnedMeshRenderer), "blendShape." + shape),
                AnimationCurve.Constant(0f, 0f, value));
            return ReplaceAsset(clip, path);
        }

        static AnimationClip ActiveClip(string path, string objPath, float value)
        {
            var clip = new AnimationClip { name = System.IO.Path.GetFileNameWithoutExtension(path) };
            AnimationUtility.SetEditorCurve(clip,
                EditorCurveBinding.FloatCurve(objPath, typeof(GameObject), "m_IsActive"),
                AnimationCurve.Constant(0f, 0f, value));
            return ReplaceAsset(clip, path);
        }

        static T ReplaceAsset<T>(T obj, string path) where T : UnityEngine.Object
        {
            // Assets gerados anteriormente nunca são apagados automaticamente.
            string safePath = AssetDatabase.GenerateUniqueAssetPath(path);
            AssetDatabase.CreateAsset(obj, safePath);
            return AssetDatabase.LoadAssetAtPath<T>(safePath);
        }

        // ---- menu helpers

        static UnityEngine.Object CreateMenu(Type tMenu, string path)
        {
            var menu = ScriptableObject.CreateInstance(tMenu);
            return ReplaceAsset(menu, path);
        }

        static void FillMenu(UnityEngine.Object menu, List<Action<SerializedProperty>> items)
        {
            var so = new SerializedObject(menu);
            var controls = so.FindProperty("controls");
            if (controls == null) return;
            if (items.Count > 8) throw new InvalidOperationException("Tentativa de criar menu com mais de 8 controles.");
            controls.arraySize = items.Count;
            for (int i = 0; i < items.Count; i++) items[i](controls.GetArrayElementAtIndex(i));
            so.ApplyModifiedProperties();
            EditorUtility.SetDirty(menu);
        }

        static void Toggle(SerializedProperty c, string label, string parameter, float value)
        {
            c.FindPropertyRelative("name").stringValue = label;
            SetEnum(c.FindPropertyRelative("type"), "Toggle");
            var p = c.FindPropertyRelative("parameter");
            if (p != null) p.FindPropertyRelative("name").stringValue = parameter;
            var v = c.FindPropertyRelative("value"); if (v != null) v.floatValue = value;
        }

        static void SubMenu(SerializedProperty c, string label, UnityEngine.Object sub)
        {
            c.FindPropertyRelative("name").stringValue = label;
            SetEnum(c.FindPropertyRelative("type"), "SubMenu");
            var sm = c.FindPropertyRelative("subMenu"); if (sm != null) sm.objectReferenceValue = sub;
        }
    }
}
