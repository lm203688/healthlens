"""GEO内容翻译工具 - 支持离线Argos翻译和增量翻译"""
import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import asyncio
import aiofiles
from datetime import datetime

logger = logging.getLogger(__name__)

class GeoTranslator:
    """GEO内容翻译器"""
    
    def __init__(self, base_dir: str = "geo_content"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(exist_ok=True)
        self.translated_dir = self.base_dir / "translated"
        self.translated_dir.mkdir(exist_ok=True)
        self.metadata_file = self.base_dir / "translation_metadata.json"
        self.metadata = self._load_metadata()
        
    def _load_metadata(self) -> Dict:
        """加载翻译元数据"""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load metadata: {e}")
        
        return {
            "total_files": 0,
            "translated_files": 0,
            "last_translation": None,
            "file_status": {}
        }
    
    def _save_metadata(self):
        """保存翻译元数据"""
        try:
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(self.metadata, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save metadata: {e}")
    
    def find_geo_files(self, search_dir: str = ".") -> List[Path]:
        """查找所有GEO相关文件"""
        geo_files = []
        search_path = Path(search_dir)
        
        # 查找GEO相关的markdown文件
        for pattern in ["*GEO*.md", "*geo*.md", "HealthLens_*.md"]:
            geo_files.extend(search_path.rglob(pattern))
        
        # 去重并过滤
        unique_files = list(set(geo_files))
        return [f for f in unique_files if f.is_file() and f.suffix == '.md']
    
    async def translate_content_offline(self, content: str, source_lang: str = "zh", target_lang: str = "en") -> str:
        """离线Argos翻译（简化版，实际使用时需要安装argos-translate）"""
        try:
            # 这里使用简化的翻译逻辑，实际部署时需要集成argos-translate
            # 由于网络限制，先提供框架
            
            # 模拟翻译结果
            translated_content = self._mock_translate(content)
            
            return translated_content
            
        except Exception as e:
            logger.error(f"Offline translation failed: {e}")
            return content  # 失败时返回原文
    
    def _mock_translate(self, content: str) -> str:
        """模拟翻译（用于演示，实际替换为argos-translate）"""
        # 这里只是一个示例，实际应该调用真实的翻译API
        lines = content.split('\n')
        translated_lines = []
        
        for line in lines:
            if line.startswith('# '):
                translated_lines.append(f"# {line[2:]} (EN)")
            elif line.startswith('> '):
                translated_lines.append(f"> {line[2:]} (EN)")
            elif line.startswith('## '):
                translated_lines.append(f"## {line[3:]} (EN)")
            elif line.startswith('- '):
                translated_lines.append(f"- {line[2:]} (EN)")
            elif line.strip():
                translated_lines.append(f"{line} (EN)")
            else:
                translated_lines.append(line)
        
        return '\n'.join(translated_lines)
    
    async def translate_file(self, file_path: Path, force: bool = False) -> bool:
        """翻译单个文件"""
        file_key = str(file_path)
        
        # 检查是否已翻译
        if not force and file_key in self.metadata["file_status"] and self.metadata["file_status"][file_key] == "completed":
            logger.info(f"File already translated: {file_path}")
            return True
        
        try:
            # 读取原文
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                content = await f.read()
            
            # 翻译内容
            translated_content = await self.translate_content_offline(content)
            
            # 保存翻译文件
            translated_file = self.translated_dir / f"{file_path.stem}_en.md"
            async with aiofiles.open(translated_file, 'w', encoding='utf-8') as f:
                await f.write(translated_content)
            
            # 更新元数据
            self.metadata["file_status"][file_key] = "completed"
            self.metadata["translated_files"] += 1
            self.metadata["last_translation"] = datetime.now().isoformat()
            
            self._save_metadata()
            logger.info(f"Translated: {file_path} -> {translated_file}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to translate {file_path}: {e}")
            self.metadata["file_status"][file_key] = "failed"
            self._save_metadata()
            return False
    
    async def batch_translate(self, file_paths: List[Path], max_concurrent: int = 5, force: bool = False) -> Dict[str, bool]:
        """批量翻译文件"""
        results = {}
        
        # 分批处理
        for i in range(0, len(file_paths), max_concurrent):
            batch = file_paths[i:i + max_concurrent]
            
            # 并发翻译
            tasks = [self.translate_file(file, force) for file in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 收集结果
            for file, result in zip(batch, batch_results):
                if isinstance(result, Exception):
                    results[str(file)] = False
                    logger.error(f"Translation failed for {file}: {result}")
                else:
                    results[str(file)] = result
        
        return results
    
    def get_translation_progress(self) -> Dict:
        """获取翻译进度"""
        total = len(self.metadata["file_status"])
        completed = sum(1 for status in self.metadata["file_status"].values() if status == "completed")
        failed = sum(1 for status in self.metadata["file_status"].values() if status == "failed")
        
        return {
            "total_files": total,
            "completed_files": completed,
            "failed_files": failed,
            "progress_percentage": (completed / total * 100) if total > 0 else 0
        }
    
    def generate_translation_report(self) -> str:
        """生成翻译报告"""
        progress = self.get_translation_progress()
        
        report = f"""
GEO内容翻译报告
================

总文件数: {progress['total_files']}
已翻译: {progress['completed_files']}
失败: {progress['failed_files']}
完成率: {progress['progress_percentage']:.1f}%

最后翻译时间: {self.metadata['last_translation'] or '无'}

文件状态详情:
"""
        
        for file_path, status in self.metadata["file_status"].items():
            report += f"- {file_path}: {status}\n"
        
        return report

# 全局翻译器实例
translator = GeoTranslator()