import re
import chardet
import tempfile
import os
import logging
from typing import List, Dict, Any
from bs4 import BeautifulSoup
import ebooklib
from ebooklib import epub
import pdfplumber

# 屏蔽 pdfminer 底层的烦人警告
logging.getLogger("pdfminer").setLevel(logging.ERROR)

# ==========================================
# 核心正则与噪音配置 (全字符兼容·最终极版)
# ==========================================
# 囊括全宇宙所有的中文数字、阿拉伯数字、以及各种被误用的零（〇○◯ＯoO0）和空格
NUMBER_CHARS = r'[一二三四五六七八九十百千万兩两零〇○◯ＯoO0-9\s]'

# 强化一级: 完美识别类似 "第一○回", "第 一 回", "第10章" 等所有格式
LEVEL1_PATTERN = re.compile(rf'^第{NUMBER_CHARS}{{1,10}}[章节卷部回集篇]([\s、:：].*)?$')

# 强化二级: 兼容英文 Chapter 与纯数字标题带分隔符
LEVEL2_PATTERN = re.compile(rf'^(Chapter\s*[IVXLCDM\d]+|{NUMBER_CHARS}{{1,10}}[\s、:：]+.*)$', re.IGNORECASE)

# 强化三级: 纯数字章节
LEVEL3_PATTERN = re.compile(rf'^{NUMBER_CHARS}{{1,5}}$')

NOISE_KEYWORDS = [
    '求推荐', '求月票', '求收藏', '上架感言', '请假条',
    '本章完', '感谢盟主', '作者的话', '新书预告',
    '点击收藏', '投票', '打赏', '正版订阅'
]

# ==========================================
# 工具函数
# ==========================================
def is_chapter_title_line(line: str, custom_regex: str = None) -> bool:
    line = line.strip()
    
    # 1. 最高优先级：自定义正则
    if custom_regex:
        try:
            if re.search(custom_regex, line, re.IGNORECASE):
                return True
        except:
            pass

    # 2. 长度与特征封杀：放宽到 80 字以兼容超长标题
    if not line or len(line) > 80:
        return False
        
    # 排除典型的正文叙事连接词（防止正文残句伪装）
    if any(keyword in line for keyword in ['说道：', '心想：', '却说那', '且说这', '只听得']):
        return False
        
    # 3. 核心正则匹配 (如果这里中了，就算标题带逗号也会直接放行！)
    if LEVEL1_PATTERN.match(line) or LEVEL2_PATTERN.match(line):
        return True
        
    if LEVEL3_PATTERN.match(line):
        # 剥离空格后判断是否为常见年份
        stripped = re.sub(r'\s+', '', line)
        if stripped.isdigit() and int(stripped) > 1000:
            return False
        return True
        
    # 4. 终极严格兜底匹配
    if ('章' in line or '卷' in line or '回' in line or '节' in line):
        # 绝不允许包含正文中常见的标点
        if re.search(r'[。！？\?\!，,；;：“”「」『』\.\-\(（《》…=]', line):
            return False
        if len(line) <= 25: 
            return True
            
    return False

def rebuild_paragraph(text: str) -> str:
    lines = text.split('\n')
    result = []
    current_paragraph = ""
    end_punctuation = {'。', '！', '？', '；', '”', '.', '!', '?', '"', "'", '」', '』'}
    
    for line in lines:
        line = line.strip()
        if not line:
            if current_paragraph:
                result.append(current_paragraph)
                current_paragraph = ""
            continue
        if not current_paragraph:
            current_paragraph = line
        else:
            if current_paragraph[-1] in end_punctuation:
                result.append(current_paragraph)
                current_paragraph = line
            else:
                current_paragraph += line
    if current_paragraph:
        result.append(current_paragraph)
    return '\n\n'.join(result)

def process_raw_text(raw_text: str, default_title: str, custom_regex: str = None) -> Dict[str, Any]:
    lines = raw_text.splitlines()
    chapters = []
    current_chapter_id = 0
    current_title = "前言/楔子"
    current_content_lines = []
    
    for line in lines:
        clean_line = line.strip()
        if any(keyword in clean_line for keyword in NOISE_KEYWORDS):
            continue
            
        if is_chapter_title_line(clean_line, custom_regex):
            if current_content_lines:
                final_content = rebuild_paragraph('\n'.join(current_content_lines))
                if final_content.strip():
                    chapters.append({
                        "chapter_id": current_chapter_id,
                        "chapter_title": current_title,
                        "word_count": len(final_content),
                        "content": final_content,
                        "volume": None
                    })
            current_chapter_id += 1
            current_title = clean_line
            current_content_lines = []
        else:
            if clean_line:
                current_content_lines.append(clean_line)
                
    if current_content_lines:
        final_content = rebuild_paragraph('\n'.join(current_content_lines))
        if final_content.strip():
            chapters.append({
                "chapter_id": current_chapter_id,
                "chapter_title": current_title,
                "word_count": len(final_content),
                "content": final_content,
                "volume": None
            })
            
    return {
        "base_info": {
            "title": default_title,
            "author": "未知",
            "word_count": sum(c['word_count'] for c in chapters),
            "chapter_count": len(chapters)
        },
        "chapters": chapters
    }

def parse_txt(file_bytes: bytes, file_name: str, custom_regex: str = None) -> Dict[str, Any]:
    detected = chardet.detect(file_bytes[:10000])
    encoding = detected['encoding'] or 'utf-8'
    try:
        raw_text = file_bytes.decode(encoding, errors='ignore')
    except:
        raw_text = file_bytes.decode('utf-8', errors='ignore')
    return process_raw_text(raw_text, file_name.replace('.txt', ''), custom_regex)

def parse_pdf(file_bytes: bytes, file_name: str, custom_regex: str = None) -> Dict[str, Any]:
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        full_text = ""
        with pdfplumber.open(tmp_path) as pdf:
            for page in pdf.pages:
                page_height = page.height
                crop_box = (0, page_height * 0.1, page.width, page_height * 0.9)
                cropped_page = page.crop(crop_box)
                text = cropped_page.extract_text()
                if text:
                    full_text += text + "\n"
        return process_raw_text(full_text, file_name.replace('.pdf', ''), custom_regex)
    finally:
        os.remove(tmp_path)

def parse_epub(file_bytes: bytes, file_name: str, custom_regex: str = None) -> Dict[str, Any]:
    with tempfile.NamedTemporaryFile(delete=False, suffix='.epub') as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        book = epub.read_epub(tmp_path)
        title_meta = book.get_metadata('DC', 'title')
        title = title_meta[0][0] if title_meta else file_name.replace('.epub', '')
        author_meta = book.get_metadata('DC', 'creator')
        author = author_meta[0][0] if author_meta else "未知"

        full_text = ""
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            soup = BeautifulSoup(item.get_content(), 'html.parser')
            for tag in soup(['script', 'style', 'img', 'nav']):
                tag.decompose()
            text = soup.get_text(separator='\n\n').strip()
            if text:
                full_text += text + "\n\n"

        parsed_result = process_raw_text(full_text, title, custom_regex)
        parsed_result['base_info']['author'] = author
        
        return parsed_result
    finally:
        os.remove(tmp_path)