#!/bin/bash
# 同步 JARVIS 源码到本地发布目录

SOURCE="/mnt/d/jarvis-assistant"
TARGET="/mnt/d/JARVIS-LOCAL"

echo "=== 同步 JARVIS LOCAL v1.1.0 ==="
echo "源目录: $SOURCE"
echo "目标目录: $TARGET"
echo ""

# 同步 Python 模块
echo "同步 jarvis 模块..."
mkdir -p "$TARGET/jarvis"
cp -v "$SOURCE"/jarvis/*.py "$TARGET/jarvis/"

# 同步技能目录
echo ""
echo "同步技能目录..."
mkdir -p "$TARGET/jarvis/skills"
cp -rv "$SOURCE"/jarvis/skills/* "$TARGET/jarvis/skills/"

# 同步静态文件
echo ""
echo "同步静态文件..."
mkdir -p "$TARGET/jarvis/static"
cp -rv "$SOURCE"/jarvis/static/* "$TARGET/jarvis/static/"

# 同步配置文件
echo ""
echo "同步配置文件..."
cp -v "$SOURCE/pyproject.toml" "$TARGET/"
cp -v "$SOURCE/README.md" "$TARGET/"
cp -v "$SOURCE/RELEASE_NOTES_v1.1.0.md" "$TARGET/"
cp -v "$SOURCE/OPTIMIZATION_CONTEXT.md" "$TARGET/"

# 更新版本信息
echo ""
echo "更新版本信息..."
cat > "$TARGET/BUILD-INFO.json" << 'BUILDEOF'
{
    "app": "JARVIS LOCAL",
    "version": "1.1.0",
    "edition": "Windows x64 complete offline voice",
    "built_at": "2026-08-20T18:00:00.0000000Z",
    "python": "Python 3.12.10"
}
BUILDEOF

echo ""
echo "=== 同步完成! ==="
echo "已同步文件:"
find "$TARGET/jarvis" -name "*.py" | wc -l
echo "个 Python 模块"
find "$TARGET/jarvis/skills" -type d | wc -l
echo "个技能目录"
