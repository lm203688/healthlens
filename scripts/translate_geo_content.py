#!/usr/bin/env python3
"""GEO内容翻译管理脚本

用法:
    python translate_geo_content.py --find          # 查找所有GEO文件
    python translate_geo_content.py --translate      # 翻译所有文件
    python translate_geo_content.py --batch 10      # 批量翻译10个文件
    python translate_geo_content.py --progress      # 查看翻译进度
    python translate_geo_content.py --report        # 生成翻译报告
    python translate_geo_content.py --reset         # 重置翻译状态
"""

import argparse
import asyncio
import logging
from pathlib import Path
import sys

# 添加项目根目录到Python路径
sys.path.append(str(Path(__file__).parent.parent))

from app.utils.geo_translator import translator

def setup_logging():
    """设置日志"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

def find_geo_files():
    """查找所有GEO文件"""
    print("🔍 查找GEO文件...")
    files = translator.find_geo_files()
    
    print(f"找到 {len(files)} 个GEO文件:")
    for i, file in enumerate(files, 1):
        print(f"{i:3d}. {file}")
    
    return files

async def translate_all_files():
    """翻译所有文件"""
    print("🌍 开始翻译所有GEO文件...")
    
    files = translator.find_geo_files()
    if not files:
        print("❌ 未找到任何GEO文件")
        return
    
    print(f"📝 将翻译 {len(files)} 个文件...")
    
    # 批量翻译
    results = await translator.batch_translate(files, max_concurrent=3)
    
    # 统计结果
    success = sum(1 for r in results.values() if r)
    failed = len(results) - success
    
    print(f"✅ 翻译完成: {success} 成功, {failed} 失败")
    
    if failed > 0:
        print("❌ 失败的文件:")
        for file_path, success in results.items():
            if not success:
                print(f"  - {file_path}")

async def translate_batch(count: int):
    """批量翻译指定数量的文件"""
    print(f"📝 批量翻译 {count} 个文件...")
    
    files = translator.find_geo_files()
    if not files:
        print("❌ 未找到任何GEO文件")
        return
    
    # 取前count个文件
    batch_files = files[:count]
    print(f"🎯 将翻译 {len(batch_files)} 个文件:")
    for i, file in enumerate(batch_files, 1):
        print(f"{i}. {file}")
    
    # 批量翻译
    results = await translator.batch_translate(batch_files, max_concurrent=3)
    
    # 统计结果
    success = sum(1 for r in results.values() if r)
    failed = len(results) - success
    
    print(f"✅ 批量翻译完成: {success} 成功, {failed} 失败")

def show_progress():
    """显示翻译进度"""
    progress = translator.get_translation_progress()
    
    print("📊 翻译进度:")
    print(f"总文件数: {progress['total_files']}")
    print(f"已翻译: {progress['completed_files']}")
    print(f"失败: {progress['failed_files']}")
    print(f"完成率: {progress['progress_percentage']:.1f}%")
    
    if progress['total_files'] > 0:
        print("\n📈 进度条:")
        bar_length = 50
        filled_length = int(bar_length * progress['progress_percentage'] / 100)
        bar = '█' * filled_length + '-' * (bar_length - filled_length)
        print(f"|{bar}| {progress['progress_percentage']:.1f}%")

def show_report():
    """显示翻译报告"""
    print("📋 GEO内容翻译报告")
    print("=" * 50)
    print(translator.generate_translation_report())

def reset_translation():
    """重置翻译状态"""
    print("🔄 重置翻译状态...")
    
    # 删除翻译文件
    import shutil
    if translator.translated_dir.exists():
        shutil.rmtree(translator.translated_dir)
        print("✅ 已删除翻译文件")
    
    # 重置元数据
    translator.metadata = {
        "total_files": 0,
        "translated_files": 0,
        "last_translation": None,
        "file_status": {}
    }
    translator._save_metadata()
    print("✅ 已重置翻译元数据")

async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="GEO内容翻译管理脚本")
    parser.add_argument("--find", action="store_true", help="查找所有GEO文件")
    parser.add_argument("--translate", action="store_true", help="翻译所有文件")
    parser.add_argument("--batch", type=int, help="批量翻译指定数量的文件")
    parser.add_argument("--progress", action="store_true", help="查看翻译进度")
    parser.add_argument("--report", action="store_true", help="生成翻译报告")
    parser.add_argument("--reset", action="store_true", help="重置翻译状态")
    
    args = parser.parse_args()
    
    setup_logging()
    
    if args.find:
        find_geo_files()
    elif args.translate:
        await translate_all_files()
    elif args.batch:
        await translate_batch(args.batch)
    elif args.progress:
        show_progress()
    elif args.report:
        show_report()
    elif args.reset:
        reset_translation()
    else:
        print("❌ 请指定一个操作参数")
        parser.print_help()

if __name__ == "__main__":
    asyncio.run(main())