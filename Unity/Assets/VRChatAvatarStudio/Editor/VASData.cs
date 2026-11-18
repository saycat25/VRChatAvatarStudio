// VRChat Avatar Studio - dados do arquivo .vrcavatar.json (lidos com JsonUtility)
using System;

namespace VRChatAvatarStudio.EditorTools
{
    [Serializable] public class VASBone { public string name; public int parent; public float[] position; }
    [Serializable] public class VASHuman { public string human; public string bone; }
    [Serializable] public class VASEyes { public string left; public string right; }
    [Serializable] public class VASPhysBone { public string root; public string kind; public string[] bones; public float[] endpoint; }
    [Serializable] public class VASShape { public string name; public int[] indices; public float[] deltas; }

    [Serializable]
    public class VASMesh
    {
        public string name;
        public string label;
        public string category;
        public bool toggle;
        public float[] positions;
        public float[] normals;
        public float[] uv;
        public int[] triangles;
        public int[] boneIndices;
        public float[] boneWeights;
        public VASShape[] blendshapes;
    }

    [Serializable]
    public class VASAvatarData
    {
        public string format;
        public int version;
        public string name;
        public string paletteTexture;
        public float[] viewPosition;
        public VASBone[] bones;
        public VASHuman[] humanoid;
        public VASEyes eyes;
        public VASPhysBone[] physbones;
        public VASMesh[] meshes;
        public string rank;
        public string specJson;
    }
}
