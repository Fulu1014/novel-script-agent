from openai import OpenAI
import os
import time
import re

# ==========================================
# Prompt 提示词工程 (注入终极防遗漏与格式死命令)
# ==========================================
EXTRACT_PROMPT = """你是一个资深的文学编辑和剧本策划。
请阅读以下小说的开篇/核心章节文本，提取出小说的【初始全局设定】（The Bible）。
必须包含：1. 核心人物小传 2. 核心世界观 3. 初始剧情脉络
【警告】：字数必须严格控制在 800 字以内，精炼核心！"""

UPDATE_PROMPT = """你是一个严谨的影视剧组“场记”与“剧情统筹”。
你的任务是根据最新一章内容，更新现有的【全局设定】。
【原则】：像写编年史一样，旧章节的细枝末节必须被删减，只保留对主线有影响的骨架。整体字数【绝对不能超过 1500 字】！直接输出更新后的文本，不要多余解释。"""

ADAPTATION_PROMPT = """你是一个拥有三十年经验的好莱坞编剧。
你的任务是将传入的小说原著【片段】，显微级无损地改编成专业的影视剧本格式。

【不可逾越的红线指令】：
1. 1比1无损还原：你必须将【当前必须改编的原著片段】从第一个字到最后一个字全部改编完！绝不允许遗漏原著片段末尾的任何动作和对话！
2. 绝对禁止重复：对照【前文剧本】，绝不要把前文已经写过的剧情再写一遍！必须紧贴前文最后一个字无缝接力往下写！
3. 严禁擅自杀青：除非当前片段是真正的大结局，否则【绝对禁止】在剧本末尾加上“（画面渐隐）”、“（本幕结束）”等断章词汇！必须保持动作的开放性，以便下文接力！
4. 场景格式：只需输出【场景 X】，不要输出其他任何乱七八糟的标题结构。

【标准剧本输出格式】：
【场景 X】
标题：内景/外景，地点，时间
角色：[登场人物]
描述：[环境描写与细致的动作细节，画面感极强]
对话：
角色名：（神态/动作描写）台词
"""

# ==========================================
# 核心 Agent 类
# ==========================================
class ScriptAdaptationAgent:
    def __init__(self, api_key: str, model_name: str):
        self.client = OpenAI(api_key=api_key, base_url="https://api.siliconflow.cn/v1")
        self.model_name = model_name

    def _call_api_with_retry(self, messages: list, temperature: float, max_tokens: int, max_retries: int = 5) -> str:
        """带指数退避和防截断无缝续写的底层 API"""
        full_content = ""
        current_messages = messages.copy()
        continuations = 0
        max_continuations = 5 
        
        while continuations <= max_continuations:
            finish_reason = None
            for attempt in range(max_retries):
                try:
                    response = self.client.chat.completions.create(
                        model=self.model_name,
                        messages=current_messages,
                        temperature=temperature,
                        max_tokens=max_tokens
                    )
                    choice = response.choices[0]
                    content = choice.message.content or ""
                    finish_reason = choice.finish_reason
                    
                    full_content += content
                    
                    if finish_reason == 'length':
                        print(f"⚠️ 输出达到 Token 上限，触发自动无缝续写...")
                        current_messages.append({"role": "assistant", "content": content})
                        current_messages.append({"role": "user", "content": "检测到你的输出被系统长度截断了。请严格紧接上一句话的最后一个字继续往下写，绝不要重复前面的内容。"})
                        break 
                    else:
                        return full_content
                        
                except Exception as e:
                    if attempt < max_retries - 1:
                        sleep_time = 5 * (2 ** attempt)
                        print(f"API 调用受阻: {e}。等待 {sleep_time} 秒重试...")
                        time.sleep(sleep_time)
                        continue
                    return full_content + f"\n\n❌_ERROR_FATAL: API 连续 {max_retries} 次报错: {str(e)}"
            
            if finish_reason != 'length':
                break
            continuations += 1
            
        return full_content

    def _split_into_chunks(self, text: str, max_length: int = 800) -> list:
        """核心切分：保持 800 字的显微级切片"""
        paragraphs = text.split('\n')
        chunks = []
        current_chunk = ""
        for p in paragraphs:
            p = p.strip()
            if not p: continue
            if len(current_chunk) + len(p) > max_length and current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = p + "\n"
            else:
                current_chunk += p + "\n"
        if current_chunk:
            chunks.append(current_chunk.strip())
        return chunks

    def _format_scene_numbers(self, script: str) -> str:
        """【终极物理防线】：完全剥夺大模型的计数权，用 Python 代码强制重排场景编号"""
        counter = 1
        def repl(match):
            nonlocal counter
            res = f"【场景 {counter}】"
            counter += 1
            return res
        # 将所有类似 【场景 5】、【场景 X】 的标记，全部按顺序重写为 1, 2, 3...
        return re.sub(r'【场景\s*\w*】', repl, script)

    def extract_global_setting(self, context_text: str) -> str:
        messages = [{"role": "system", "content": EXTRACT_PROMPT}, {"role": "user", "content": f"【小说开篇文本】：\n{context_text[:12000]}"}]
        return self._call_api_with_retry(messages, temperature=0.3, max_tokens=1500)

    def update_global_setting(self, current_setting: str, chapter_title: str, chapter_content: str) -> str:
        user_message = (
            f"【当前的全局设定】：\n{current_setting}\n\n"
            f"=================\n"
            f"【最新章节】：{chapter_title}\n"
            f"【本章正文】：\n{chapter_content[:15000]}\n\n" 
            f"请将本章的新内容融入并浓缩更新全局设定："
        )
        messages = [{"role": "system", "content": UPDATE_PROMPT}, {"role": "user", "content": user_message}]
        result = self._call_api_with_retry(messages, temperature=0.2, max_tokens=2000)
        return current_setting if "❌_ERROR_FATAL" in result else result

    def adapt_chapter(self, chapter_title: str, chapter_content: str, global_setting: str, progress_callback=None) -> str:
        chunks = self._split_into_chunks(chapter_content, max_length=800)
        full_script = ""
        
        for idx, chunk in enumerate(chunks):
            if progress_callback:
                progress_callback(idx + 1, len(chunks))
                
            tail_context = full_script[-1000:] if full_script else "无（本章开篇）"
            next_preview = chunks[idx+1][:200] if idx + 1 < len(chunks) else "无（本章已完结）"
                
            user_message = (
                f"【当前全局设定】：\n{global_setting}\n\n"
                f"=================\n"
                f"【前文剧本（仅供衔接参考，绝不可再写一遍）】：\n{tail_context}\n\n"
                f"=================\n"
                f"【下文剧情预告（仅供参考走向，绝不要提前把下文的剧情写出来）】：\n{next_preview}\n\n"
                f"=================\n"
                f"【当前必须改编的原著片段（显微级无损还原！）】：\n{chunk}\n\n"
                f"请开始对【当前必须改编的原著片段】进行剧本化：\n"
                f"警告：你生成的结尾必须精确对应原著片段的最后一个字！绝不可遗漏！"
            )
            
            messages = [{"role": "system", "content": ADAPTATION_PROMPT}, {"role": "user", "content": user_message}]
            script_part = self._call_api_with_retry(messages, temperature=0.7, max_tokens=3000)
            
            if "❌_ERROR_FATAL" in script_part:
                return full_script + "\n\n" + script_part
                
            full_script += script_part + "\n\n"
            time.sleep(1.5) 
            
        # 在整章改编完之后，启动 Python 级别的终极重排引擎，净化所有乱七八糟的场景编号！
        full_script = self._format_scene_numbers(full_script)
        return full_script.strip()

    # === 文件与存档系统 ===
    def get_safe_title(self, book_title: str) -> str:
        return "".join([c for c in book_title if c.isalnum() or c in ['-', '_', ' ']]).rstrip()

    def append_to_local_file(self, book_title: str, chapter_title: str, script_content: str) -> str:
        if not os.path.exists("output"): os.makedirs("output")
        file_path = os.path.join("output", f"《{self.get_safe_title(book_title)}》_完整剧本.txt")
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(f"\n\n{'='*20} {chapter_title} {'='*20}\n\n")
            f.write(script_content)
            f.write("\n")
        return file_path

    def save_setting_checkpoint(self, book_title: str, setting_content: str) -> str:
        if not os.path.exists("output"): os.makedirs("output")
        file_path = os.path.join("output", f"《{self.get_safe_title(book_title)}》_全局设定存档.txt")
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(setting_content)
        return file_path