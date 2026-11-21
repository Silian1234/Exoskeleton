using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;

// Builds an exoskeleton tier bundle from a GPT model (Assets/EXO/<tier>/exo_unity.json + textures).
// Structure is taken from the ripped Redut prefab (DressItem / PreviewPivot / Loot / Skin with EFT Skin LODs),
// but ALL Redut geometry is replaced: skinned LODs = exo LOD0/LOD1 (up to 4 bones per vertex, EFT bindposes),
// loot meshes = static exo meshes. One material with the tier textures on the Redut shader (re-pointed after build).
// usage: Unity -batchmode -executeMethod ExoTierBuild.Build -exoTier T1
public static class ExoTierBuild
{
    const string RipPrefab = "Assets/Rip/Prefab/item_equipment_armor_redut_T5.prefab";
    const string ShaderPath = "Assets/Shaders/Reflect-BumpSpecSMap.shader";
    const string OutDir = "C:/SPT/_fullbody_armor/exoskeleton/build";

    [Serializable] class BoneInfo { public string name; public string path; public float[] bindpose; }
    [Serializable] class Lod { public float[] v; public float[] n; public float[] uv; public int[] t; public int[] bi; public float[] bw; }
    [Serializable] class Data { public BoneInfo[] bones; public Lod[] lods; }

    static string Arg(string name, string def)
    {
        var a = Environment.GetCommandLineArgs();
        int i = Array.IndexOf(a, name);
        return i >= 0 && i + 1 < a.Length ? a[i + 1] : def;
    }

    static void Tex(string path, bool normal, bool srgb)
    {
        var ti = (TextureImporter)AssetImporter.GetAtPath(path) ?? throw new Exception("missing " + path);
        ti.textureType = normal ? TextureImporterType.NormalMap : TextureImporterType.Default;
        ti.sRGBTexture = srgb; ti.mipmapEnabled = true; ti.maxTextureSize = 2048;
        ti.SaveAndReimport();
    }

    static Mesh MakeMesh(Lod l, Matrix4x4[] bind, bool skinned, string name)
    {
        int n = l.v.Length / 3;
        var verts = new Vector3[n]; var norms = new Vector3[n]; var uvs = new Vector2[n]; var bws = new BoneWeight[n];
        for (int i = 0; i < n; i++)
        {
            verts[i] = new Vector3(l.v[i * 3], l.v[i * 3 + 1], l.v[i * 3 + 2]);
            norms[i] = new Vector3(l.n[i * 3], l.n[i * 3 + 1], l.n[i * 3 + 2]);
            uvs[i] = new Vector2(l.uv[i * 2], l.uv[i * 2 + 1]);
            bws[i] = new BoneWeight
            {
                boneIndex0 = l.bi[i * 4], weight0 = l.bw[i * 4], boneIndex1 = l.bi[i * 4 + 1], weight1 = l.bw[i * 4 + 1],
                boneIndex2 = l.bi[i * 4 + 2], weight2 = l.bw[i * 4 + 2], boneIndex3 = l.bi[i * 4 + 3], weight3 = l.bw[i * 4 + 3]
            };
        }
        var m = new Mesh { name = name, indexFormat = UnityEngine.Rendering.IndexFormat.UInt32 };
        m.vertices = verts; m.normals = norms; m.uv = uvs;
        m.SetTriangles(l.t, 0);
        if (skinned) { m.boneWeights = bws; m.bindposes = bind; }
        m.RecalculateTangents(); m.RecalculateBounds();
        return m;
    }

    public static void Build()
    {
        string tier = Arg("-exoTier", "T1");
        string dir = $"Assets/EXO/{tier}";
        string suffix = tier == "T1" ? "" : "_" + tier.ToLower();
        string outPrefabDir = "Assets/Content/Items/Equipment/Exoskeleton";
        string outPrefab = $"{outPrefabDir}/item_equipment_exoskeleton{suffix}.prefab";
        string bundle = $"assets/content/items/equipment/exoskeleton/item_equipment_exoskeleton{suffix}.bundle";

        foreach (var b in AssetDatabase.GetAllAssetBundleNames()) AssetDatabase.RemoveAssetBundleName(b, true);
        Directory.CreateDirectory(outPrefabDir); Directory.CreateDirectory("Assets/FBA/Gen"); Directory.CreateDirectory($"{dir}/Gen");
        var shader = AssetDatabase.LoadAssetAtPath<Shader>(ShaderPath) ?? throw new Exception("placeholder shader missing");
        var cube = AssetDatabase.LoadAssetAtPath<Cubemap>("Assets/FBA/Gen/placeholder_cube.cubemap");
        if (cube == null) { cube = new Cubemap(4, TextureFormat.RGBA32, false); AssetDatabase.CreateAsset(cube, "Assets/FBA/Gen/placeholder_cube.cubemap"); }
        var phys = AssetDatabase.LoadAssetAtPath<PhysicMaterial>("Assets/FBA/Gen/placeholder_phys.physicMaterial");
        if (phys == null) { phys = new PhysicMaterial("placeholder_phys"); AssetDatabase.CreateAsset(phys, "Assets/FBA/Gen/placeholder_phys.physicMaterial"); }

        Tex($"{dir}/exo_dif.png", false, true); Tex($"{dir}/exo_gloss.png", false, true); Tex($"{dir}/exo_nrm.png", true, false);

        // material: Redut material properties (EFT shader params) with the tier textures
        var redutMat = AssetDatabase.LoadAssetAtPath<Material>("Assets/Rip/Mat/item_equipment_armor_redut_T5.mat");
        var so = new SerializedObject(redutMat); so.FindProperty("m_Shader").objectReferenceValue = shader; so.ApplyModifiedPropertiesWithoutUndo();
        var matPath = $"{dir}/Gen/exo_{tier.ToLower()}.mat";
        AssetDatabase.DeleteAsset(matPath);
        var mat = new Material(redutMat) { name = $"exo_{tier.ToLower()}" };
        mat.SetTexture("_MainTex", AssetDatabase.LoadAssetAtPath<Texture2D>($"{dir}/exo_dif.png"));
        mat.SetTexture("_BumpMap", AssetDatabase.LoadAssetAtPath<Texture2D>($"{dir}/exo_nrm.png"));
        mat.SetTexture("_SpecMap", AssetDatabase.LoadAssetAtPath<Texture2D>($"{dir}/exo_gloss.png"));
        mat.SetTexture("_Cube", cube);
        AssetDatabase.CreateAsset(mat, matPath);
        var so2 = new SerializedObject(mat); so2.FindProperty("m_Shader").objectReferenceValue = shader; so2.ApplyModifiedPropertiesWithoutUndo();

        var data = JsonUtility.FromJson<Data>(File.ReadAllText($"{dir}/exo_unity.json"));
        var paths = data.bones.Select(b => b.path).ToArray();
        var bind = data.bones.Select(b =>
        {
            var m = new Matrix4x4();
            for (int r = 0; r < 4; r++) for (int c = 0; c < 4; c++) m[r, c] = b.bindpose[c * 4 + r];
            return m;
        }).ToArray();

        var go = (GameObject)UnityEngine.Object.Instantiate(AssetDatabase.LoadAssetAtPath<GameObject>(RipPrefab));
        go.name = $"item_equipment_exoskeleton{suffix}";

        // skinned LODs
        var skins = go.GetComponentsInChildren<Diz.Skinning.Skin>(true);
        if (skins.Length != 2) throw new Exception("expected 2 skin LODs, found " + skins.Length);
        for (int lod = 0; lod < 2; lod++)
        {
            var mesh = MakeMesh(data.lods[lod], bind, true, $"exo_{tier.ToLower()}_lod{lod}");
            var mp = $"{dir}/Gen/{mesh.name}.asset"; AssetDatabase.DeleteAsset(mp); AssetDatabase.CreateAsset(mesh, mp);
            var smr = skins[lod]._skinnedMeshRenderer;
            smr.sharedMesh = mesh;
            smr.sharedMaterials = new[] { mat };
            smr.localBounds = new Bounds(Vector3.zero, new Vector3(2.4f, 2.4f, 2.4f));
            smr.updateWhenOffscreen = false;
            skins[lod]._bonePaths = paths;
            skins[lod]._rootBonePath = "Root_Joint/Base HumanPelvis";
            Debug.Log($"EXO {tier} lod{lod}: verts {mesh.vertexCount} tris {mesh.triangles.Length / 3} bones {paths.Length}");
        }

        // loot (dropped item): static exo meshes, colliders fitted to them
        var loots = go.GetComponentsInChildren<MeshFilter>(true);
        for (int i = 0; i < loots.Length; i++)
        {
            var mesh = MakeMesh(data.lods[Math.Min(i, 1)], bind, false, $"exo_{tier.ToLower()}_loot{i}");
            var mp = $"{dir}/Gen/{mesh.name}.asset"; AssetDatabase.DeleteAsset(mp); AssetDatabase.CreateAsset(mesh, mp);
            loots[i].sharedMesh = mesh;
            var r = loots[i].GetComponent<MeshRenderer>(); if (r != null) r.sharedMaterials = new[] { mat };
            var bc = loots[i].GetComponent<BoxCollider>();
            if (bc != null) { bc.center = mesh.bounds.center; bc.size = mesh.bounds.size; }
        }
        foreach (var col in go.GetComponentsInChildren<Collider>(true)) col.sharedMaterial = phys;

        AssetDatabase.DeleteAsset(outPrefab);
        PrefabUtility.SaveAsPrefabAsset(go, outPrefab);
        UnityEngine.Object.DestroyImmediate(go);

        AssetImporter.GetAtPath(outPrefab).assetBundleName = bundle;
        AssetImporter.GetAtPath(ShaderPath).assetBundleName = "shaders";
        AssetImporter.GetAtPath("Assets/FBA/Gen/placeholder_cube.cubemap").assetBundleName = "cubemaps";
        AssetImporter.GetAtPath("Assets/FBA/Gen/placeholder_phys.physicMaterial").assetBundleName = "assets/commonassets/physics/physicsmaterials.bundle";
        AssetDatabase.SaveAssets();
        Directory.CreateDirectory(OutDir);
        var manifest = BuildPipeline.BuildAssetBundles(OutDir,
            BuildAssetBundleOptions.UncompressedAssetBundle | BuildAssetBundleOptions.DeterministicAssetBundle, BuildTarget.StandaloneWindows64)
            ?? throw new Exception("build failed");
        foreach (var b in manifest.GetAllAssetBundles()) Debug.Log("EXO bundle: " + b);
    }
}
