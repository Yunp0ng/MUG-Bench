import http.client
import json
import os
import time
import glob
import datetime
import re
import argparse
import itertools
import threading
from tqdm import tqdm

# ================= CONFIGURATION =================
DEFAULT_API_KEYS = os.getenv("ACMMM_API_KEYS", os.getenv("ACMMM_JUDGE_API_KEY", ""))
API_HOST = os.getenv("ACMMM_JUDGE_API_HOST", "yunwu.ai")
API_PATH = os.getenv("ACMMM_JUDGE_API_PATH", "/v1/chat/completions")

# [修改点] 定义不同等级使用的模型
MODEL_L1_L2 = os.getenv("ACMMM_QA_MODEL_L1_L2", "gpt-4o")
MODEL_L3 = os.getenv("ACMMM_QA_MODEL_L3", "gpt-5")

# 路径配置
SOURCE_MEETING_DIR = os.getenv("SOURCE_MEETING_DIR", "data/Real_meeting")
DEFAULT_EVIDENCE_ROOT = os.getenv("EVIDENCE_ROOT", "out")
EVIDENCE_DIRS = {
    "L1": os.getenv("EVIDENCE_DIR_L1", os.path.join(DEFAULT_EVIDENCE_ROOT, "L1", "Evidence")),
    "L2": os.getenv("EVIDENCE_DIR_L2", os.path.join(DEFAULT_EVIDENCE_ROOT, "L2", "Evidence")),
    "L3": os.getenv("EVIDENCE_DIR_L3", os.path.join(DEFAULT_EVIDENCE_ROOT, "L3", "Evidence")),
}
FINAL_OUTPUT_ROOT = os.getenv("FINAL_OUTPUT_ROOT", "out/Benchmark_QA")
LOG_FILE = os.path.join(FINAL_OUTPUT_ROOT, "api_log_gen.jsonl")
DEFAULT_LEVELS = os.getenv("QA_LEVELS", "L1,L2,L3")

# ================= SYSTEM PROMPTS (去偏设计) =================

PROMPT_L1_L2 = """你是一个专业的会议阅读理解出题专家。
我将提供一组【脱离上下文的会议证据片段】以及相关的【主题分析】。
请基于这些信息构造一个高质量的问答对。

### 构造原则 (模拟无知用户)
1. **提问视角**：问题(Question)必须像是一个没看过会议记录、但想了解会议内容的人问的。
   - *Bad:* "张三说的三个竞品是什么？" (泄露了说话人和数量)
   - *Good:* "会议中提到了哪些竞争对手？" (用户只关心业务事实)
2. **答案忠实**：答案(Answer)必须完全基于提供的证据，不得编造。
3. **综合性**：(针对L2) 答案必须综合分散在多句话里的信息。

### 输出格式 (JSON)
{"question": "...", "answer": "..."}
"""

PROMPT_L3 = """你是一个高阶商业会议分析师。
我将提供一组【包含复杂逻辑的证据片段】以及对该逻辑的【专家解读(Reasoning)】。
请构造一个具有挑战性的问答对，测试 AI 是否能看穿表象，抓住核心结论。

### 构造原则 (针对结果提问)
1. **利用专家解读**：请参考提供的 Reasoning 来理解反转或噪音逻辑，确保答案准确反映最终决策。
2. **严禁泄露过程**：
   - 问题**只能**问"最终决定是什么？"或"关于X的结论是什么？"。
   - **绝对不要问**"为什么A被否决？" (这泄露了A被否决的事实)。
3. **抗干扰**：如果Reasoning指出存在噪音，答案必须排除这些噪音。
4. **答案解释**：答案除了给出结论，最好简要说明理由。

### 输出格式 (JSON)
{"question": "...", "answer": "..."}
"""

RESPONSE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "generate_qa_pair",
        "schema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "构造的问题"},
                "answer": {"type": "string", "description": "标准答案"}
            },
            "required": ["question", "answer"],
            "additionalProperties": False
        },
        "strict": True
    }
}

def log_api_call(file_name, level, status, response_text, duration):
    try:
        log_dir = os.path.dirname(LOG_FILE)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        log_entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "file": file_name,
            "level": level,
            "status": status,
            "duration": round(duration, 2),
            "response_preview": response_text[:200] if response_text else "None",
            "full_response": response_text
        }
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"日志写入失败: {e}")

def clean_json_response(content):
    if not content: return content
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(json)?", "", content, flags=re.IGNORECASE)
        content = re.sub(r"```$", "", content)
    return content.strip()

def load_source_map(file_name):
    path = os.path.join(SOURCE_MEETING_DIR, file_name)
    if not os.path.exists(path):
        candidates = glob.glob(os.path.join(SOURCE_MEETING_DIR, "*"))
        for c in candidates:
            if os.path.basename(c) == file_name:
                path = c
                break
    if not os.path.exists(path): return None

    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        speaker_map = {str(s['speaker_id']): s['name'] for s in data.get('speakers', [])}
        id_map = {}
        for utt in data.get('utterances', []):
            uid = utt['id']
            spk_id = str(utt.get('speaker_id'))
            spk_name = speaker_map.get(spk_id, "Unknown")
            id_map[uid] = f"{spk_name}: {utt.get('text', '')}"
        return id_map
    except Exception as e:
        print(f"Error loading source {file_name}: {e}")
        return None

KEY_CYCLE = None
KEY_LOCK = threading.Lock()


def parse_api_keys(api_keys_str):
    keys = [x.strip() for x in api_keys_str.split(",") if x.strip()]
    if not keys:
        raise RuntimeError("Missing ACMMM_API_KEYS / ACMMM_JUDGE_API_KEY for qa_gen.py")
    return keys


def next_api_key():
    global KEY_CYCLE
    with KEY_LOCK:
        return next(KEY_CYCLE)


def generate_qa_pair(evidence_text, level, file_name, meta_info):
    """
    调用 API 生成 QA
    meta_info: 包含 topic, reasoning, pattern 等信息的字典
    """
    system_prompt = PROMPT_L3 if level == "L3" else PROMPT_L1_L2
    
    # [修改点] 根据等级选择模型
    current_model = MODEL_L3 if level == "L3" else MODEL_L1_L2
    
    topic_str = meta_info.get('topic', '未知')
    reasoning_str = meta_info.get('reasoning', '无')
    pattern_str = meta_info.get('pattern', '')
    
    context_block = f"""
【辅助分析信息】
- 证据主题: {topic_str}
- 逻辑分析: {reasoning_str}
"""
    if pattern_str:
        context_block += f"- 逻辑模式: {pattern_str}\n"

    user_prompt = f"""以下是会议中的证据片段：
---
{evidence_text}
---
{context_block}

请基于证据片段和辅助分析信息，生成一个高质量的QA对："""
    
    payload_str = json.dumps({
        "model": current_model,  # 使用选定的模型
        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        "response_format": RESPONSE_SCHEMA,
        "temperature": 0.2 
    }, ensure_ascii=False)
    
    payload_bytes = payload_str.encode('utf-8')
    
    start_time = time.time()
    
    for attempt in range(3):
        api_key = next_api_key()
        try:
            headers = {
                'Accept': 'application/json',
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json; charset=utf-8'
            }
            conn = http.client.HTTPSConnection(API_HOST, timeout=int(os.getenv("ACMMM_QA_TIMEOUT", "90")))
            conn.request("POST", API_PATH, payload_bytes, headers)
            res = conn.getresponse()
            data = res.read()
            res_data_str = data.decode("utf-8")
            
            duration = time.time() - start_time
            log_api_call(file_name, level, res.status, res_data_str, duration)
            
            if res.status != 200:
                if res.status == 429: time.sleep(10)
                else: time.sleep(2)
                continue

            cleaned_str = clean_json_response(res_data_str)
            try:
                response_json = json.loads(cleaned_str)
            except json.JSONDecodeError:
                try:
                    raw_json = json.loads(res_data_str)
                    if "error" in raw_json:
                        time.sleep(2)
                        continue
                    content_str = raw_json.get("choices", [{}])[0].get("message", {}).get("content")
                    cleaned_content_str = clean_json_response(content_str)
                    return json.loads(cleaned_content_str)
                except:
                    time.sleep(2)
                    continue

            if "question" in response_json and "answer" in response_json:
                return response_json
            
            if "choices" in response_json:
                content_str = response_json["choices"][0]["message"]["content"]
                cleaned_content_str = clean_json_response(content_str)
                return json.loads(cleaned_content_str)
                
            return None

        except Exception as e:
            duration = time.time() - start_time
            log_api_call(file_name, level, f"EXCEPTION:{attempt+1}", str(e), duration)
            time.sleep(2)
            
    return None

def process_level(level):
    input_dir = EVIDENCE_DIRS[level]
    output_dir = os.path.join(FINAL_OUTPUT_ROOT, level)
    if not os.path.exists(output_dir): os.makedirs(output_dir)
    if not os.path.exists(input_dir):
        print(f"Skipping {level}, input dir not found.")
        return

    evidence_files = glob.glob(os.path.join(input_dir, "*.json"))
    print(f"--- Processing {level} ({len(evidence_files)} files) ---")
    
    for evid_file in tqdm(evidence_files, desc=f"Gen QA {level}"):
        evid_base_name = os.path.basename(evid_file)
        if evid_base_name.startswith("evidence_"):
            core_name = evid_base_name.replace("evidence_", "", 1)
        else:
            core_name = evid_base_name
            
        target_file_name = f"{core_name}"
        final_out_path = os.path.join(output_dir, target_file_name)
        if os.path.exists(final_out_path): continue
            
        try:
            with open(evid_file, 'r', encoding='utf-8') as f:
                evid_data = json.load(f)
            
            source_file = evid_data.get("source_file") or core_name
            id_map = load_source_map(source_file)
            if not id_map:
                id_map = load_source_map(core_name)
                if not id_map: continue
            
            final_samples = []
            groups = evid_data.get("evidence_groups", [])
            
            for idx, group in enumerate(groups):
                ids = group.get("ids", [])
                valid_ids = [i for i in ids if i in id_map]
                if not valid_ids: continue
                
                evidence_text = "\n".join([f"[{i}] {id_map[i]}" for i in valid_ids])
                
                meta_info = {
                    "topic": group.get("topic", ""),
                    "reasoning": group.get("reasoning", ""),
                    "pattern": group.get("pattern", "")
                }
                
                qa_pair = generate_qa_pair(evidence_text, level, core_name, meta_info)
                
                if qa_pair and "question" in qa_pair and "answer" in qa_pair:
                    sample = {
                        "query_id": f"{core_name}_{level}_{idx}",
                        "level": level,
                        "topic": group.get("topic"),
                        "pattern": group.get("pattern", "N/A"),
                        "reasoning_from_mining": group.get("reasoning"), 
                        "question": qa_pair["question"],
                        "gold_answer": qa_pair["answer"],
                        "evidence_ids": valid_ids
                    }
                    final_samples.append(sample)
            
            if final_samples:
                with open(final_out_path, 'w', encoding='utf-8') as f:
                    json.dump({
                        "source_file": source_file, 
                        "level": level,
                        "sample_count": len(final_samples),
                        "samples": final_samples
                    }, f, ensure_ascii=False, indent=2)
                    
        except Exception as e:
            tqdm.write(f"Error processing {evid_file}: {e}")

def parse_levels(levels_str):
    levels = [x.strip().upper() for x in levels_str.split(",") if x.strip()]
    for lv in levels:
        if lv not in {"L1", "L2", "L3"}:
            raise ValueError(f"Unsupported level: {lv}")
    return levels


def main():
    global KEY_CYCLE
    parser = argparse.ArgumentParser(description="Generate benchmark QA from mined evidence")
    parser.add_argument("--levels", default=DEFAULT_LEVELS, help="comma-separated levels, e.g. L2,L3")
    args = parser.parse_args()
    api_keys = parse_api_keys(DEFAULT_API_KEYS)
    KEY_CYCLE = itertools.cycle(api_keys)
    if not os.path.exists(FINAL_OUTPUT_ROOT):
        os.makedirs(FINAL_OUTPUT_ROOT)
    for level in parse_levels(args.levels):
        process_level(level)

if __name__ == '__main__':
    main()
