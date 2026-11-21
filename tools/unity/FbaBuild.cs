using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;

// Builds the FullBodyArmor carrier bundle:
//  Redut-T5 prefab (ripped) + limb plates merged into both skinned LODs as a 2nd submesh.
//  Shader / cubemap / physics material are placeholders put into bundles named like the game's,
//  their references are re-pointed to the game's CABs/pathIDs by tools/patch_bundle.py after the build.
public static class ExoskeletonBuild
{
    const string RipPrefab = "Assets/Rip/Prefab/item_equipment_armor_redut_T5.prefab";
    const string ShaderPath = "Assets/Shaders/Reflect-BumpSpecSMap.shader";
    const string OutPrefabDir = "Assets/Content/Items/Equipment/Exoskeleton";
    const string OutPrefab = OutPrefabDir + "/item_equipment_exoskeleton.prefab";
    const string BundleName = "assets/content/items/equipment/exoskeleton/item_equipment_exoskeleton.bundle";
    const string OutDir = "C:/SPT/_fullbody_armor/exoskeleton/build";

    [Serializable] class BoneInfo { public string name; public string path; public float[] bindpose; }
    [Serializable] class PlateInfo { public string name; public string bone; public float[] v; public float[] n; public float[] uv; public int[] t; }
    [Serializable] class Data { public PlateInfo[] plates; public BoneInfo[] bones; }

    static void SetBundle(string path, string bundle)
    {
        var imp = AssetImporter.GetAtPath(path);
        if (imp == null) throw new Exception("no importer for " + path);
        imp.assetBundleName = bundle;
    }

    static void Tex(string path, bool normal, bool srgb)
    {
        var ti = (TextureImporter)AssetImporter.GetAtPath(path);
        ti.textureType = normal ? TextureImporterType.NormalMap : TextureImporterType.Default;
        ti.sRGBTexture = srgb;
        ti.mipmapEnabled = true;
        ti.SaveAndReimport();
    }

    static Material Placeholderize(Material m, Shader sh)
    {
        // keep saved properties; just point at the placeholder shader
        var so = new SerializedObject(m);
        so.FindProperty("m_Shader").objectReferenceValue = sh;
        so.ApplyModifiedPropertiesWithoutUndo();
        return m;
    }

    public static void Build()
    {
        foreach (var n in AssetDatabase.GetAllAssetBundleNames()) AssetDatabase.RemoveAssetBundleName(n, true);
        Directory.CreateDirectory(OutPrefabDir);
        Directory.CreateDirectory("Assets/FBA/Gen");

        var shader = AssetDatabase.LoadAssetAtPath<Shader>(ShaderPath);
        if (shader == null) throw new Exception("placeholder shader missing");

        // placeholders
        var cube = AssetDatabase.LoadAssetAtPath<Cubemap>("Assets/FBA/Gen/placeholder_cube.cubemap");
        if (cube == null)
        {
            cube = new Cubemap(4, TextureFormat.RGBA32, false);
            AssetDatabase.CreateAsset(cube, "Assets/FBA/Gen/placeholder_cube.cubemap");
        }
        var phys = AssetDatabase.LoadAssetAtPath<PhysicMaterial>("Assets/FBA/Gen/placeholder_phys.physicMaterial");
        if (phys == null)
        {
            phys = new PhysicMaterial("placeholder_phys");
            AssetDatabase.CreateAsset(phys, "Assets/FBA/Gen/placeholder_phys.physicMaterial");
        }

        Tex("Assets/FBA/Tex/fba_plates_dif.png", false, true);
        Tex("Assets/FBA/Tex/fba_plates_gloss.png", false, true);
        Tex("Assets/FBA/Tex/fba_plates_nrm.png", true, false);

        // materials
        var redutMat = AssetDatabase.LoadAssetAtPath<Material>("Assets/Rip/Mat/item_equipment_armor_redut_T5.mat");
        Placeholderize(redutMat, shader);
        redutMat.SetTexture("_Cube", cube);
        EditorUtility.SetDirty(redutMat);

        var plateMatPath = "Assets/FBA/Gen/fba_plates.mat";
        AssetDatabase.DeleteAsset(plateMatPath);
        var plateMat = new Material(redutMat);
        plateMat.name = "fba_plates";
        plateMat.SetTexture("_MainTex", AssetDatabase.LoadAssetAtPath<Texture2D>("Assets/FBA/Tex/fba_plates_dif.png"));
        plateMat.SetTexture("_BumpMap", AssetDatabase.LoadAssetAtPath<Texture2D>("Assets/FBA/Tex/fba_plates_nrm.png"));
        plateMat.SetTexture("_SpecMap", AssetDatabase.LoadAssetAtPath<Texture2D>("Assets/FBA/Tex/fba_plates_gloss.png"));
        plateMat.SetTexture("_Cube", cube);
        AssetDatabase.CreateAsset(plateMat, plateMatPath);
        Placeholderize(plateMat, shader);

        // plate data
        var data = JsonUtility.FromJson<Data>(File.ReadAllText("Assets/FBA/plates_unity.json"));
        Debug.Log($"FBA plates {data.plates.Length}, bones {data.bones.Length}");

        // prefab
        var src = AssetDatabase.LoadAssetAtPath<GameObject>(RipPrefab);
        var go = (GameObject)UnityEngine.Object.Instantiate(src);
        go.name = "item_equipment_exoskeleton";

        foreach (var col in go.GetComponentsInChildren<Collider>(true)) col.sharedMaterial = phys;

        var skins = go.GetComponentsInChildren<Diz.Skinning.Skin>(true);
        Debug.Log("FBA skins: " + skins.Length);
        int lod = 0;
        foreach (var skin in skins)
        {
            var smr = skin._skinnedMeshRenderer;
            var baseMesh = smr.sharedMesh;
            var paths = skin._bonePaths.ToList();
            var bind = baseMesh.bindposes.ToList();
            int Bone(BoneInfo b)
            {
                int i = paths.IndexOf(b.path);
                if (i >= 0) return i;
                paths.Add(b.path);
                var m = new Matrix4x4();
                for (int r = 0; r < 4; r++) for (int c = 0; c < 4; c++) m[r, c] = b.bindpose[c * 4 + r];
                bind.Add(m);
                return paths.Count - 1;
            }
            var boneIndex = data.bones.ToDictionary(b => b.name, b => Bone(b));

            var verts = baseMesh.vertices.ToList();
            var norms = baseMesh.normals.ToList();
            var tans = baseMesh.tangents.ToList();
            var uv0 = baseMesh.uv.ToList();
            var bw = baseMesh.boneWeights.ToList();
            int baseCount = verts.Count;
            var subTris = new List<int>();
            foreach (var p in data.plates)
            {
                int off = verts.Count;
                int bi = boneIndex[p.bone];
                for (int i = 0; i < p.v.Length / 3; i++)
                {
                    verts.Add(new Vector3(p.v[i * 3], p.v[i * 3 + 1], p.v[i * 3 + 2]));
                    norms.Add(new Vector3(p.n[i * 3], p.n[i * 3 + 1], p.n[i * 3 + 2]));
                    tans.Add(new Vector4(1, 0, 0, 1));
                    uv0.Add(new Vector2(p.uv[i * 2], p.uv[i * 2 + 1]));
                    bw.Add(new BoneWeight { boneIndex0 = bi, weight0 = 1f });
                }
                foreach (var t in p.t) subTris.Add(t + off);
            }

            var mesh = new Mesh();
            mesh.name = baseMesh.name + "_fba";
            mesh.indexFormat = UnityEngine.Rendering.IndexFormat.UInt32;
            mesh.SetVertices(verts);
            mesh.SetNormals(norms);
            mesh.SetUVs(0, uv0);
            mesh.subMeshCount = baseMesh.subMeshCount + 1;
            for (int s = 0; s < baseMesh.subMeshCount; s++) mesh.SetTriangles(baseMesh.GetTriangles(s), s);
            mesh.SetTriangles(subTris, baseMesh.subMeshCount);
            mesh.boneWeights = bw.ToArray();
            mesh.bindposes = bind.ToArray();
            mesh.RecalculateTangents();
            mesh.RecalculateBounds();
            var meshPath = $"Assets/FBA/Gen/{mesh.name}.asset";
            AssetDatabase.DeleteAsset(meshPath);
            AssetDatabase.CreateAsset(mesh, meshPath);

            smr.sharedMesh = mesh;
            var mats = smr.sharedMaterials.ToList();
            while (mats.Count < baseMesh.subMeshCount) mats.Add(redutMat);
            for (int i = 0; i < mats.Count; i++) mats[i] = redutMat;
            mats.Add(redutMat); // plates are UV-mapped onto the Redut atlas (camo panel + webbing)
            smr.sharedMaterials = mats.ToArray();
            smr.localBounds = new Bounds(Vector3.zero, new Vector3(2.4f, 2.4f, 2.4f));
            smr.updateWhenOffscreen = false;
            skin._bonePaths = paths.ToArray();
            Debug.Log($"FBA lod{lod++}: {baseMesh.name} verts {baseCount}->{verts.Count} bones {paths.Count} submeshes {mesh.subMeshCount}");
        }

        // also reassign loot renderers to the placeholder-shader redut material (same asset)
        foreach (var r in go.GetComponentsInChildren<MeshRenderer>(true))
        {
            var ms = r.sharedMaterials;
            for (int i = 0; i < ms.Length; i++) ms[i] = redutMat;
            r.sharedMaterials = ms;
        }

        AssetDatabase.DeleteAsset(OutPrefab);
        PrefabUtility.SaveAsPrefabAsset(go, OutPrefab);
        UnityEngine.Object.DestroyImmediate(go);

        SetBundle(OutPrefab, BundleName);
        SetBundle(ShaderPath, "shaders");
        SetBundle("Assets/FBA/Gen/placeholder_cube.cubemap", "cubemaps");
        SetBundle("Assets/FBA/Gen/placeholder_phys.physicMaterial", "assets/commonassets/physics/physicsmaterials.bundle");
        AssetDatabase.SaveAssets();

        Directory.CreateDirectory(OutDir);
        var manifest = BuildPipeline.BuildAssetBundles(OutDir,
            BuildAssetBundleOptions.UncompressedAssetBundle | BuildAssetBundleOptions.DeterministicAssetBundle,
            BuildTarget.StandaloneWindows64);
        if (manifest == null) throw new Exception("build failed");
        foreach (var b in manifest.GetAllAssetBundles())
            Debug.Log("FBA bundle: " + b + " deps: " + string.Join(",", manifest.GetAllDependencies(b)));
    }
}
