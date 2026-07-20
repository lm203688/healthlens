"""中医古籍数据导入脚本
从 txt 文件导入食疗方、本草条目到数据库

Usage:
    # 导入书目索引
    python scripts/import_tcm_books.py --books /path/to/中医古籍txt合集

    # 导入食疗方
    python scripts/import_tcm_books.py --food-therapy /path/to/中医古籍txt合集

    # 全部导入
    python scripts/import_tcm_books.py --all /path/to/中医古籍txt合集
"""
import re
import sys
import json
import uuid
import argparse
from pathlib import Path


def parse_index_md(md_path: str) -> list[dict]:
    """解析古籍分类索引 markdown，提取书目信息"""
    books = []
    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Match patterns like: | 001 | 《神农本草经》 | 作者 | 朝代 | ... |
    # or numbered lines
    pattern = re.compile(r"\|\s*(\d+)\s*\|\s*[《]?([^》|\n]+)[》]?\s*\|\s*([^|\n]*)\|\s*([^|\n]*)")
    for m in pattern.finditer(content):
        books.append({
            "title": m.group(2).strip(),
            "author": m.group(3).strip() or None,
            "dynasty": m.group(4).strip() or None,
        })

    # Fallback: try line patterns if table didn't match
    if not books:
        lines = content.split("\n")
        for line in lines:
            if re.match(r"^\d+", line):
                parts = re.split(r"[\s|]+", line.strip(), maxsplit=4)
                if len(parts) >= 2:
                    books.append({
                        "title": parts[1].strip().strip("《》"),
                        "author": parts[2].strip() if len(parts) > 2 else None,
                        "dynasty": parts[3].strip() if len(parts) > 3 else None,
                    })

    return books


def parse_food_therapy_file(file_path: str) -> list[dict]:
    """解析食疗方 txt 文件，提取食疗配方"""
    recipes = []
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Split by 篇名 blocks
    blocks = re.split(r"<篇名>(.+?)(?=\n<篇名>|\Z)", content, flags=re.DOTALL)

    for i in range(1, len(blocks), 2):
        name = blocks[i].strip()
        body = blocks[i + 1] if i + 1 < len(blocks) else ""

        # Skip book-level header (first entry is usually the book name)
        if name in ("食疗方", "食疗本草"):
            continue

        recipe = {"name": name}

        # Extract attributes
        attr_match = re.search(r"属性[：:]\s*(.+?)(?:\n\n|\n〔)", body)
        if attr_match:
            recipe["ingredients_text"] = attr_match.group(1).strip()

        ind_match = re.search(r"〔主疗[〕]〕\s*(.+?)(?:\n\n|\n〔)", body)
        if ind_match:
            recipe["indications"] = ind_match.group(1).strip()

        method_match = re.search(r"〔方法[〕]〕\s*(.+?)(?:\n\n|\n〔|\Z)", body, re.DOTALL)
        if method_match:
            recipe["method"] = method_match.group(1).strip().replace("\n", "")

        content_match = re.search(r"内容[：:]\s*(.+?)(?:\n\n|\n〔|\Z)", body, re.DOTALL)
        if content_match:
            recipe["method"] = recipe.get("method") or content_match.group(1).strip().replace("\n", "")

        # Extract ingredients from food therapy format
        ingredients = {}
        if recipe.get("ingredients_text"):
            for item_match in re.finditer(r"〔(.+?)〕(.+?)(?:〔|$)", recipe["ingredients_text"]):
                ingredients[item_match.group(1)] = item_match.group(2).strip()

        if recipe.get("method") or recipe.get("indications"):
            recipe["ingredients"] = ingredients if ingredients else None
            recipes.append(recipe)

    return recipes


def parse_herb_entry(name: str, body: str) -> dict:
    """解析本草条目"""
    entry = {"name": name}

    # Extract property/flavor (属性标记 like 〈温〉 〈寒〉 〈平〉)
    prop_match = re.search(r"[〈<](.+?)[〉>]", name)
    if prop_match:
        entry["property"] = prop_match.group(1)

    # Extract content
    content_match = re.search(r"内容[：:]\s*(.+?)(?:\n\n|\n〈|\Z)", body, re.DOTALL)
    if content_match:
        entry["content"] = content_match.group(1).strip()

    return entry


def determine_category(title: str) -> str:
    """根据书名判断分类"""
    if any(kw in title for kw in ["本草"]):
        return "本草"
    if any(kw in title for kw in ["方", "剂"]):
        return "方剂"
    if any(kw in title for kw in ["食疗", "食鉴", "食治"]):
        return "食疗"
    if any(kw in title for kw in ["针灸", "针经", "灸"]):
        return "针灸"
    if any(kw in title for kw in ["脉", "诊"]):
        return "诊法"
    if any(kw in title for kw in ["伤寒", "温病", "瘟疫"]):
        return "温病"
    if any(kw in title for kw in ["妇科", "妇人", "产"]):
        return "妇科"
    if any(kw in title for kw in ["儿科", "幼科", "婴童"]):
        return "儿科"
    if any(kw in title for kw in ["外科", "疡", "疮"]):
        return "外科"
    return "综合"


def import_to_database(books: list[dict], recipes: list[dict], source_book: str = ""):
    """导入到数据库"""
    try:
        from app.database import SessionLocal
        from app.models.tcm_knowledge import TcmClassicalBook, FoodTherapyRecipe

        session = SessionLocal()

        # Import books
        if books:
            for book_data in books:
                existing = session.query(TcmClassicalBook).filter_by(
                    title=book_data["title"]
                ).first()
                if not existing:
                    book = TcmClassicalBook(
                        id=str(uuid.uuid4()),
                        title=book_data["title"],
                        author=book_data.get("author"),
                        dynasty=book_data.get("dynasty"),
                        category=determine_category(book_data["title"]),
                    )
                    session.add(book)
            session.commit()
            print(f"[OK] Imported {len(books)} books")

        # Import recipes
        if recipes:
            for rec in recipes:
                existing = session.query(FoodTherapyRecipe).filter_by(
                    name=rec["name"], source_book=source_book
                ).first()
                if not existing:
                    recipe = FoodTherapyRecipe(
                        id=str(uuid.uuid4()),
                        name=rec["name"],
                        source_book=source_book or rec.get("source"),
                        dynasty=rec.get("dynasty"),
                        category=rec.get("category"),
                        ingredients=rec.get("ingredients") or rec.get("ingredients_text"),
                        indications=rec.get("indications"),
                        method=rec.get("method"),
                    )
                    session.add(recipe)
            session.commit()
            print(f"[OK] Imported {len(recipes)} food therapy recipes")

        session.close()
    except ImportError:
        print("[WARN] Cannot import database modules. Running in dry mode.")
        if books:
            print(f"[DRY] Would import {len(books)} books")
        if recipes:
            print(f"[DRY] Would import {len(recipes)} recipes")


def main():
    parser = argparse.ArgumentParser(description="Import TCM classical books data")
    parser.add_argument("--books", help="Directory of TCM txt files")
    parser.add_argument("--food-therapy", help="Directory containing 食疗方.txt and 食疗本草.txt")
    parser.add_argument("--index", help="Path to index markdown file")
    parser.add_argument("--all", help="Directory containing all TCM data")
    args = parser.parse_args()

    base_dir = args.all or args.books or args.food_therapy or "."

    # Import food therapy
    ft_dir = args.food_therapy or args.all
    if ft_dir:
        for ft_file in ["食疗方.txt", "食疗本草.txt"]:
            ft_path = Path(ft_dir) / "中医古籍txt合集" / ft_file
            if not ft_path.exists():
                ft_path = Path(ft_dir) / ft_file
            if ft_path.exists():
                recipes = parse_food_therapy_file(str(ft_path))
                source_book = ft_path.stem.replace(".txt", "")
                import_to_database([], recipes, source_book=source_book)
                print(f"[OK] Parsed {len(recipes)} recipes from {ft_file}")

    # Import book index
    if args.all or args.books:
        index_path = args.index or Path(base_dir) / ".." / "使用说明-中医古籍分类索引.md"
        if Path(index_path).exists():
            books = parse_index_md(str(index_path))
            if books:
                import_to_database(books, [])
                print(f"[OK] Parsed {len(books)} books from index")
        else:
            print(f"[WARN] Index file not found: {index_path}")


if __name__ == "__main__":
    main()