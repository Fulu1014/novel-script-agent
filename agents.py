from openai import OpenAI
import os
import time
import re
import httpx
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

# ==========================================
# Prompt 提示词工程 (长期记忆版 & 好莱坞工业级版)
# ==========================================
EXTRACT_PROMPT = """你是一个资深的文学编辑和剧本策划。
请阅读以下小说的开篇/核心章节文本，提取出小说的【初始全局设定】（The Bible）。
必须包含：1. 核心人物小传 2. 核心世界观 3. 初始剧情脉络
【警告】：字数必须严格控制在 800 字以内，精炼核心！"""

UPDATE_PROMPT = """你是一个严谨的影视剧组“场记”与“剧情统筹”。
你的任务是根据最新一章内容，更新现有的【全局设定】。
【原则】：像写编年史一样，旧章节的细枝末节必须被删减，只保留对主线有影响的骨架。整体字数【绝对不能超过 1500 字】！直接输出更新后的文本，不要多余解释。"""

ADAPTATION_PROMPT = """你是一个拥有三十年经验的顶级影视编剧，现在正在操刀一部【S级古装神话大片】的剧本改编。
你的任务是将传入的小说原著【片段】，显微级无损地改编成专业的影视剧本格式。

【绝密编剧军规 - 违反将导致项目流产】：
1. 严禁重复交代世界观：【当前全局设定】仅供你了解背景，绝对不可在剧本中写出设定里的背景！只允许老老实实写【当前必须改编的原著片段】里正在发生的事！不要一上来就拍宇宙开辟！
2. 像素级剧情还原：绝对不许跳过任何过场文戏或交代性剧情（如接旨、视察、交谈等），剧情遗漏率为 0！
3. 诗词赋文必须保留：原著中的经典诗词赋，必须通过 [画外音/旁白 (V.O.)] 吟诵，或者结合 [特写镜头 (CU)] 的环境展示出来，保留古典神话韵味！
4. 丰满群戏与背景：绝不能只写主角！必须加入原著片段中的群戏描述（如群猴的反应、天兵的神态、水族的动作），丰富画面的层次感和环境音。
5. 半文半白台词：台词严禁完全口语化/现代派！必须保留原著中医、道、释的专业术语及古风质感，适度保留文言神韵。
6. 时间与蒙太奇：善用 [蒙太奇 (Montage)] 展现时间流转、昼夜交替或长途跋涉，让剧情过渡顺滑。
7. 绝对禁止重复前文：对照【前文剧本】，紧贴前文最后一个动作无缝接力往下拍！严禁擅自杀青！

【标准剧本输出格式】：
【场景 X】
标题：[内景/外景]，[具体地点]，[时间（日/夜/暮/晨）]
角色：[登场所有角色，包括群演]
视觉与动作：[极具画面感的环境描写、动作细节、群戏反应、蒙太奇过渡]
旁白/对白：
(V.O. 旁白)：（原著诗词或背景音）
角色名：（神态/小动作）带有古风韵味的台词
"""

# ==========================================
# 核心 Agent 类
# ==========================================
class ScriptAdaptationAgent:
    def __init__(self, api_key: str, model_name: str, book_title: str):
        self.api_key = api_key
        self.model_name = model_name
        self.book_title = book_title
        
        # 自定义底层网络客户端：设置 120 秒超时防止长文本生成时断连
        # (已移除强行绕过代理的 trust_env=False，使用时请确保已手动关闭科学上网)
        custom_http_client = httpx.Client(
            timeout=httpx.Timeout(timeout=120.0, connect=30.0) 
        )
        
        self.client = OpenAI(
            api_key=api_key, 
            base_url="https://api.siliconflow.cn/v1",
            http_client=custom_http_client
        )
        
        self.embeddings = OpenAIEmbeddings(
            openai_api_key=api_key,
            openai_api_base="https://api.siliconflow.cn/v1",
            model="BAAI/bge-m3",
            http_client=custom_http_client 
        )
        
        # 🚨 数据隔离：为每本书生成独立的记忆存储路径
        safe_title = self.get_safe_title(book_title)
        self.memory_path = f"output/{safe_title}_faiss_memory"
        
        self.long_term_memory = None

        if os.path.exists(self.memory_path):
            try:
                self.long_term_memory = FAISS.load_local(self.memory_path, self.embeddings, allow_dangerous_deserialization=True)
                print(f"✅ 成功加载《{book_title}》的专属长期记忆库！")
            except:
                print(f"⚠️ 《{book_title}》的本地向量库加载失败，将重新建立。")

    def _call_api_with_retry(self, messages: list, temperature: float, max_tokens: int, max_retries: int = 5) -> str:
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

    # --- 🧠 LangChain 长期记忆管理模块 ---
    def _add_to_long_term_memory(self, chapter_title: str, script_content: str):
        doc = Document(page_content=script_content, metadata={"chapter": chapter_title})
        if self.long_term_memory is None:
            self.long_term_memory = FAISS.from_documents([doc], self.embeddings)
        else:
            self.long_term_memory.add_documents([doc])
        if not os.path.exists("output"): os.makedirs("output")
        self.long_term_memory.save_local(self.memory_path)

    def _retrieve_long_term_memory(self, query_text: str, k: int = 2) -> str:
        if self.long_term_memory is None:
            return "无相关历史记忆。"
        docs = self.long_term_memory.similarity_search(query_text, k=k)
        retrieved_texts = []
        for i, d in enumerate(docs):
            retrieved_texts.append(f"【回忆片段 {i+1}，出自 {d.metadata['chapter']}】:\n{d.page_content[:400]}...") 
        return "\n\n".join(retrieved_texts)

    # --- 文本与状态处理模块 ---
    def _split_into_chunks(self, text: str, max_length: int = 800) -> list:
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
        counter = 1
        def repl(match):
            nonlocal counter
            res = f"【场景 {counter}】"
            counter += 1
            return res
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
        last_scene_num = 0
        
        for idx, chunk in enumerate(chunks):
            if progress_callback:
                progress_callback(idx + 1, len(chunks))
                
            matches = re.findall(r'【场景\s*(\d+)】', full_script)
            if matches: last_scene_num = int(matches[-1])
                
            tail_context = full_script[-1000:] if full_script else "无（本章开篇）"
            next_preview = chunks[idx+1][:200] if idx + 1 < len(chunks) else "无（本章已完结）"

            # 🧠 检索长期记忆
            retrieved_memory = self._retrieve_long_term_memory(chunk, k=2)
                
            user_message = (
                f"【当前全局设定 (短期核心记忆)】：\n{global_setting}\n\n"
                f"=================\n"
                f"【长期记忆检索 (相似历史剧本，用于保持人设口吻一致)】：\n{retrieved_memory}\n\n"
                f"=================\n"
                f"【前文剧本 (仅供衔接参考)】：\n{tail_context}\n\n"
                f"=================\n"
                f"【下文剧情预告 (仅供参考走向)】：\n{next_preview}\n\n"
                f"=================\n"
                f"【当前必须改编的原著片段（显微级无损还原！）】：\n{chunk}\n\n"
                f"请开始对【当前必须改编的原著片段】进行剧本化：\n"
                f"要求：当前场景编号必须从【场景 {last_scene_num + 1}】或标明 (接上场) 开始续写！"
            )
            
            messages = [{"role": "system", "content": ADAPTATION_PROMPT}, {"role": "user", "content": user_message}]
            script_part = self._call_api_with_retry(messages, temperature=0.7, max_tokens=3000)
            
            if "❌_ERROR_FATAL" in script_part:
                return full_script + "\n\n" + script_part
                
            # 🧠 存入长期记忆
            self._add_to_long_term_memory(chapter_title, script_part)
            
            full_script += script_part + "\n\n"
            time.sleep(1.5) 
            
        full_script = self._format_scene_numbers(full_script)
        return full_script.strip()

    # === 文件与存档系统 ===
    def get_safe_title(self, book_title: str) -> str:
        return "".join([c for c in book_title if c.isalnum() or c in ['-', '_', ' ']]).rstrip()

    def append_to_local_file(self, book_title: str, chapter_title: str, script_content: str) -> str:
        if not os.path.exists("output"): os.makedirs("output")
        safe_title = self.get_safe_title(book_title)
        file_path = os.path.join("output", f"《{safe_title}》_完整剧本.txt")
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(f"\n\n{'='*20} {chapter_title} {'='*20}\n\n")
            f.write(script_content)
            f.write("\n")
        return file_path

    def save_setting_checkpoint(self, book_title: str, setting_content: str) -> str:
        if not os.path.exists("output"): os.makedirs("output")
        safe_title = self.get_safe_title(book_title)
        file_path = os.path.join("output", f"《{safe_title}》_全局设定存档.txt")
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(setting_content)
        return file_path