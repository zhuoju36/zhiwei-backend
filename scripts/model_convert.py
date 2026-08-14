"""3D 模型格式转换脚本：OBJ/STL/PLY/glTF -> GLB（v0.8c）。

核心函数 convert_bytes 供 Celery 任务（app/tasks/model_tasks.py）调用；
CLI 入口供手动转换：python -m scripts.model_convert in.obj out.glb

IFC 等 BIM 语义格式需 Blender/IfcOpenShell 转换器（v0.9+），当前明确拒绝。
"""

import argparse
import io
import sys

# trimesh 加载时支持的 file_type 白名单
SUPPORTED_FORMATS = {"obj", "stl", "ply", "gltf", "glb"}


def convert_bytes(data: bytes, source_format: str) -> bytes:
    """把一种网格格式的字节流转换为 GLB 字节流。

    - glb 源文件直接透传（已是目标格式）
    - 其余格式经 trimesh 加载后导出为 GLB
    - 不支持格式抛 ValueError（IFC 等）
    """
    fmt = source_format.lower().lstrip(".")
    if fmt not in SUPPORTED_FORMATS:
        raise ValueError(
            f"不支持的格式: {source_format}（支持 {sorted(SUPPORTED_FORMATS)}；"
            "IFC 需 v0.9+ Blender/IfcOpenShell 转换器）"
        )
    if fmt == "glb":
        return data

    import trimesh

    try:
        scene = trimesh.load(io.BytesIO(data), file_type=fmt)
    except Exception as exc:  # 文件损坏 / 无网格数据
        raise ValueError(f"模型解析失败（{fmt}）: {exc}") from exc
    if scene is None:
        raise ValueError(f"模型为空（{fmt}）")

    glb = scene.export(file_type="glb")
    if not glb:
        raise ValueError(f"模型导出 GLB 失败（{fmt}）")
    return glb


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="3D 模型转换：OBJ/STL/PLY/glTF -> GLB")
    parser.add_argument("src", help="源文件路径（.obj/.stl/.ply/.gltf/.glb）")
    parser.add_argument("dst", help="输出 GLB 路径")
    args = parser.parse_args(argv)

    fmt = args.src.rsplit(".", 1)[-1].lower() if "." in args.src else ""
    with open(args.src, "rb") as f:
        data = f.read()
    try:
        glb = convert_bytes(data, fmt)
    except ValueError as exc:
        print(f"转换失败: {exc}", file=sys.stderr)
        return 1
    with open(args.dst, "wb") as f:
        f.write(glb)
    print(f"转换完成: {args.src} -> {args.dst} ({len(glb)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
