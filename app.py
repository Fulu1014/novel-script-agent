import streamlit as st
import time
import os
from parsers import parse_txt, parse_epub, parse_pdf
from agents import ScriptAdaptationAgent

st.set_page_config(page_title="小说转剧本智能助手", page_icon="🎬", layout="wide")

st.title("🎬 多 Agent 自动化剧本改编流水线")
st.markdown("解析 -> 设定 -> **[ 显微级切片 · Python物理防漏 · 编号自动重排 ]**。")

with st.sidebar:
    st.header("⚙️ 全局配置")
    api_key = st.text_input("请输入 SiliconFlow API Key", type="password")
    model_choice = st.selectbox("请选择大语言模型", ["deepseek-ai/DeepSeek-V4-Pro", "Pro/deepseek-ai/DeepSeek-V3.2", "Pro/deepseek-ai/DeepSeek-V3"])
    st.markdown("---")

if 'parsed_data' not in st.session_state:
    st.session_state.parsed_data = None
if 'global_setting' not in st.session_state:
    st.session_state.global_setting = ""

st.warning("""
**⚠️ 核心格式兼容性提示（请务必阅读）：**
虽然本系统内置了强大的多格式解析引擎，但由于网络小说排版千奇百怪，**并非所有章节标识格式的小说都能被完美拆分与改编**。
为了保证剧本能够 1 比 1 无损生成，请确保您的源文件尽量符合以下规范：
1. **优先推荐**：带有标准内部目录结构的 **EPUB** 电子书（准确率最高）。
2. **纯文本 TXT**：请确保章节标题独占一行，且包含标准的序号标识（如 `第一章`、`第1回`、`Chapter 1`、`第一○回` 等）。
3. **避免上传**：无章节标识的“流水账”长文、满篇硬回车的劣质文本。
""")

uploaded_file = st.file_uploader("1. 请上传您的小说原著", type=['txt', 'epub', 'pdf'])

if uploaded_file is not None:
    file_type = uploaded_file.name.split('.')[-1].lower()
    current_book_title = uploaded_file.name.split('.')[0]
    if st.button("🚀 启动统一解析引擎"):
        with st.spinner(f"正在对 {file_type.upper()} 格式进行智能切分..."):
            file_bytes = uploaded_file.read()
            if file_type == 'txt': st.session_state.parsed_data = parse_txt(file_bytes, uploaded_file.name)
            elif file_type == 'epub': st.session_state.parsed_data = parse_epub(file_bytes, uploaded_file.name)
            elif file_type == 'pdf': st.session_state.parsed_data = parse_pdf(file_bytes, uploaded_file.name)
            st.success("✅ 解析完成！")

if st.session_state.parsed_data:
    parsed_data = st.session_state.parsed_data
    book_title = parsed_data['base_info']['title']
    chapters = parsed_data['chapters']
    total_chap = len(chapters)
    agent = ScriptAdaptationAgent(api_key, model_choice,current_book_title)
    
    st.markdown("---")
    st.markdown(f"### 📑 《{book_title}》 剧本改编控制台")

    col1, col2 = st.columns([1, 2])
    with col1:
        st.markdown("##### 设定初始化")
        if st.button("🧠 提取全新【初始全局设定】"):
            if not api_key: st.error("请输入 API Key")
            else:
                with st.spinner("提取中..."):
                    context_source = "\n".join([c['content'] for c in chapters[:2]])
                    st.session_state.global_setting = agent.extract_global_setting(context_source)
                    agent.save_setting_checkpoint(book_title, st.session_state.global_setting)
        
        setting_file_path = os.path.join("output", f"《{agent.get_safe_title(book_title)}》_全局设定存档.txt")
        if os.path.exists(setting_file_path):
            st.info("检测到本地存在此书的存档记录。")
            if st.button("💾 恢复本地存档 (断点续传专用)"):
                with open(setting_file_path, 'r', encoding='utf-8') as f:
                    st.session_state.global_setting = f.read()
                st.success("已恢复最近的剧情设定记忆！")
                
    with col2:
        st.session_state.global_setting = st.text_area(
            "当前全局设定 (实时动态更新存档)", 
            st.session_state.global_setting, 
            height=250
        )

    st.markdown("#### ⚡ 启动动态演化流水线")
    run_mode = st.radio("选择运行模式：", ["🛠️ 灰度测试 (仅跑前 5 章)", "🎯 自定义区间跑", "🚀 挂机全本模式 (一键通关)"], horizontal=True)
    
    if "灰度" in run_mode:
        start_idx, end_idx = 0, min(4, total_chap - 1)
    elif "自定义" in run_mode:
        start_idx, end_idx = st.slider("请选择从第几章跑到第几章：", 0, total_chap - 1, (0, 0))
    else:
        start_idx, end_idx = 0, total_chap - 1
        st.warning("进入全本挂机模式。如果中途网络中断，请刷新页面，读取本地存档，并使用【自定义区间跑】从断线的章节继续！")

    if st.button("▶️ 启动改编流水线"):
        if not api_key or not st.session_state.global_setting:
            st.error("请确保已输入 API Key 并生成/恢复了全局设定！")
        else:
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            view_col1, view_col2 = st.columns(2)
            script_display = view_col1.empty()
            setting_display = view_col2.empty()
            
            total_tasks = end_idx - start_idx + 1
            saved_file_path = ""
            
            for i, current_idx in enumerate(range(start_idx, end_idx + 1)):
                target_chapter = chapters[current_idx]
                chapter_title = target_chapter['chapter_title']
                
                # 动态回调：展示底层的显微级碎片处理进度
                def update_chunk_progress(current_chunk, total_chunks):
                    status_text.markdown(f"**🎬 正在显微级无损还原:** `{chapter_title}` (内部碎片缝合 **{current_chunk}/{total_chunks}**) - 章节进度 ({i+1}/{total_tasks})")

                # A: 剧本改编 (底层的 Python 自动重排系统已启动)
                script_content = agent.adapt_chapter(
                    chapter_title, 
                    target_chapter['content'], 
                    st.session_state.global_setting,
                    progress_callback=update_chunk_progress
                )
                
                if "❌_ERROR_FATAL" in script_content:
                    st.error(f"🚨 在处理 {chapter_title} 时 API 彻底崩溃。已紧急刹车。\n请稍后恢复存档，从 {current_idx} 章重试。")
                    break 
                
                saved_file_path = agent.append_to_local_file(book_title, chapter_title, script_content)
                # 给剧本展示区也加一个动态 key，防患于未然
                script_display.text_area(f"✅ 最新剧本：{chapter_title}", script_content, height=450, key=f"script_display_{i}")
                
                status_text.markdown(f"**🧠 更新设定存档:** `{chapter_title}` ({i+1}/{total_tasks})...")
                st.session_state.global_setting = agent.update_global_setting(
                    st.session_state.global_setting, chapter_title, target_chapter['content']
                )
                agent.save_setting_checkpoint(book_title, st.session_state.global_setting) 
                
                # 🚨 核心修复：把 key 改为 f-string，拼入变量 {i}
                setting_display.text_area("🔄 进化后的全局设定", st.session_state.global_setting, height=450, key=f"unique_global_setting_display_{i}")
                
                progress_bar.progress((i + 1) / total_tasks)
                time.sleep(2) 
                
            else:
                status_text.success(f"🎉 任务圆满完成！所有1比1无损剧本(编号已完美排序)已安全落盘至：`{saved_file_path}`")