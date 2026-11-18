// VRChat Avatar Studio - estimativa heurística local (não substitui o relatório oficial do SDK)
using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;

namespace VRChatAvatarStudio.EditorTools
{
    public static class VASPerformanceCheck
    {
        static readonly string[] RankNames = { "Excellent", "Good", "Medium", "Poor", "Very Poor" };

        // nome, Excellent, Good, Medium, Poor
        static readonly object[][] Limits =
        {
            new object[] { "Triangulos", 32000, 70000, 70000, 70000 },
            new object[] { "Malhas (skinned)", 1, 2, 8, 16 },
            new object[] { "Malhas basicas", 4, 8, 16, 24 },
            new object[] { "Slots de material", 4, 8, 16, 32 },
            new object[] { "Ossos", 75, 150, 256, 400 },
            new object[] { "PhysBones (componentes)", 4, 8, 16, 32 },
            new object[] { "PhysBones (ossos afetados)", 16, 64, 128, 256 },
            new object[] { "Animators", 1, 4, 16, 32 },
        };

        public static string Run(GameObject root, List<string> log)
        {
            int tris = 0, skinned = 0, basic = 0, slots = 0;
            var boneSet = new HashSet<Transform>();
            foreach (var r in root.GetComponentsInChildren<SkinnedMeshRenderer>(true))
            {
                if (!r.gameObject.activeInHierarchy || !r.enabled) continue;
                skinned++;
                slots += r.sharedMaterials.Length;
                if (r.sharedMesh != null)
                    for (int s = 0; s < r.sharedMesh.subMeshCount; s++) tris += (int)(r.sharedMesh.GetIndexCount(s) / 3);
                foreach (var b in r.bones) if (b != null) boneSet.Add(b);
            }
            foreach (var r in root.GetComponentsInChildren<MeshRenderer>(true))
            {
                if (!r.gameObject.activeInHierarchy || !r.enabled) continue;
                basic++;
                slots += r.sharedMaterials.Length;
                var mf = r.GetComponent<MeshFilter>();
                if (mf != null && mf.sharedMesh != null)
                    for (int s = 0; s < mf.sharedMesh.subMeshCount; s++) tris += (int)(mf.sharedMesh.GetIndexCount(s) / 3);
            }

            int pbCount = 0;
            var affectedTransforms = new HashSet<Transform>();
            var tPb = VASVRChatSetup.FindType("VRC.SDK3.Dynamics.PhysBone.Components.VRCPhysBone");
            if (tPb != null)
            {
                foreach (var c in root.GetComponentsInChildren(tPb, true))
                {
                    var component = c as Component;
                    if (component == null || !component.gameObject.activeInHierarchy) continue;
                    var behaviour = component as Behaviour;
                    if (behaviour != null && !behaviour.enabled) continue;
                    pbCount++;
                    foreach (var tr in component.transform.GetComponentsInChildren<Transform>(true)) affectedTransforms.Add(tr);
                }
            }
            int pbTransforms = affectedTransforms.Count;
            int animators = 0;
            foreach (var a in root.GetComponentsInChildren<Animator>(true))
                if (a.enabled && a.gameObject.activeInHierarchy) animators++;

            var values = new[] { tris, skinned, basic, slots, boneSet.Count, pbCount, pbTransforms, animators };
            int worst = 0;
            var culprits = new List<string>();
            log.Add("--- Estimativa local heurística de desempenho (PC) ---");
            for (int i = 0; i < Limits.Length; i++)
            {
                int v = values[i], r = 4;
                for (int k = 0; k < 4; k++) { if (v <= (int)Limits[i][k + 1]) { r = k; break; } }
                log.Add(string.Format("{0}: {1}  ->  {2}", Limits[i][0], v, RankNames[r]));
                if (r > worst) { worst = r; culprits.Clear(); }
                if (r == worst && r > 0) culprits.Add((string)Limits[i][0]);
            }
            log.Add("RANKING LOCAL ESTIMADO: " + RankNames[worst] + (culprits.Count > 0 ? "  (limitado por: " + string.Join(", ", culprits.ToArray()) + ")" : ""));
            if (worst >= 2) log.Add("Dica: no programa, agrupe pecas no mesmo grupo ou ative 'Juntar tudo em 1 malha' para reduzir malhas e materiais.");
            log.Add("(Heurística parcial: não replica todas as regras/otimizações do SDK. Confirme sempre no VRChat SDK Control Panel.)");
            return RankNames[worst];
        }
    }
}
