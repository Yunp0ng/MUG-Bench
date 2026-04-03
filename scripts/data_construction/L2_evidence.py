import http.client
import json
import os
import time
import glob
import datetime
import re
from tqdm import tqdm

# ================= CONFIGURATION =================
API_KEY = os.getenv("ACMMM_JUDGE_API_KEY", "")
API_HOST = os.getenv("ACMMM_JUDGE_API_HOST", "yunwu.ai")
API_PATH = os.getenv("ACMMM_JUDGE_API_PATH", "/v1/chat/completions")
MODEL_NAME = os.getenv("ACMMM_L2_MODEL", "gpt-5")

# 路径配置
INPUT_DIR = os.getenv("MEETING_INPUT_DIR", "data/Real_meeting")
OUTPUT_DIR = os.getenv("EVIDENCE_OUTPUT_DIR_L2", "out/L2/Evidence")
LOG_FILE = os.getenv("EVIDENCE_LOG_FILE_L2", os.path.join(OUTPUT_DIR, "api_log_L2.jsonl"))

# === L2 JSON Schema ===
RESPONSE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "extract_l2_evidence",
        "schema": {
            "type": "object",
            "properties": {
                "evidence_groups": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "topic": {"type": "string", "description": "证据的主题"},
                            "ids": {"type": "array", "items": {"type": "integer"}, "description": "离散的句子ID列表"},
                            "reasoning": {"type": "string", "description": "选择理由"}
                        },
                        "required": ["topic", "ids", "reasoning"],
                        "additionalProperties": False
                    }
                }
            },
            "required": ["evidence_groups"],
            "additionalProperties": False
        },
        "strict": True
    }
}


# === System Prompt ===
SYSTEM_PROMPT = """你是一个高级信息整合专家。
你的任务是从会议记录原文中提取【Level 2: 跨轮次信息聚合】的证据片段。

### Level 2 定义
- **拼图游戏**：关于同一个具体话题的信息，散落在会议的**不同时间点**。
- **互补关系**：后文的信息是对前文的**补充**（例如：先说了时间，后说了负责人），而不是反驳。
- **形态约束**：证据 ID 必须是【离散的 (Discrete)】。第一句和最后一句的 ID 间隔建议超过 20 句。

### 任务要求
1. 寻找被多次提及的话题（例如：开头提了方案，结尾做了总结）。
2. 提取所有相关的句子 ID，组合起来必须能构成该话题的完整信息。
3. **严禁**提取存在逻辑冲突或反转的句子。
"""

def log_api_call(file_name, status, response_text, duration):
    """记录 API 调用日志"""
    try:
        log_dir = os.path.dirname(LOG_FILE)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
            
        log_entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "file": file_name,
            "status": status,
            "duration_seconds": round(duration, 2),
            "response_preview": response_text[:200] if response_text else "None",
            "full_response": response_text
        }
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"日志写入失败: {e}")

def parse_meeting_json(file_path):
    """解析会议 JSON 为带 ID 的文本"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 建立说话人映射
        speaker_map = {str(s['speaker_id']): s['name'] for s in data.get('speakers', [])}
        
        lines = []
        id_map = {} # 用于校验 ID 是否存在
        
        for utt in data.get('utterances', []):
            uid = utt['id']
            # 兼容 speaker_id 是 int 或 string
            spk_id = str(utt.get('speaker_id'))
            spk_name = speaker_map.get(spk_id, "Unknown")
            text = utt.get('text', "")
            
            line_str = f"[{uid}] {spk_name}: {text}"
            lines.append(line_str)
            id_map[uid] = line_str
            

        return "\n".join(lines), id_map
    except Exception as e:
        tqdm.write(f"解析文件 {file_path} 失败: {e}")
        return None, None

def clean_json_response(content):
    """清洗返回内容，去除可能的 markdown 标记"""
    if not content:
        return content
    content = content.strip()
    # 去除 ```json 和 ```
    if content.startswith("```"):
        content = re.sub(r"^```(json)?", "", content, flags=re.IGNORECASE)
        content = re.sub(r"```$", "", content)
    return content.strip()

def get_evidence_from_api(context, file_name, max_retries=3):
    """调用 API 获取证据，包含重试逻辑"""
    user_prompt = f"会议记录原文：\n{context}"
    
    payload = json.dumps({
        "model": MODEL_NAME,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}],
        "response_format": RESPONSE_SCHEMA,
        "temperature": 0.1 
    })
    
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {API_KEY}',
        'Content-Type': 'application/json'
    }

    start_time = time.time()
    
    for attempt in range(max_retries):
        try:
            # 设置 120秒超时，防止网络卡死
            conn = http.client.HTTPSConnection(API_HOST, timeout=720)
            conn.request("POST", API_PATH, payload, headers)
            res = conn.getresponse()
            data = res.read()
            res_data_str = data.decode("utf-8")
            
            duration = time.time() - start_time
            log_api_call(file_name, res.status, res_data_str, duration)

            if res.status != 200:
                tqdm.write(f"  [Error] API Status {res.status} (尝试 {attempt + 1})")
                if res.status == 429:
                    wait_time = 30 * (attempt + 1)
                    tqdm.write(f"    [!!] 429 限流，等待 {wait_time} 秒...")
                    time.sleep(wait_time)
                else:
                    time.sleep(5)
                continue
            
            # 清洗并解析 JSON
            cleaned_str = clean_json_response(res_data_str)
            
            try:
                response_json = json.loads(cleaned_str)
            except json.JSONDecodeError:
                # 尝试解析 API 标准返回格式
                try:
                    raw_json = json.loads(res_data_str)
                    if "error" in raw_json:
                        tqdm.write(f"  [Error] API Error Body: {raw_json}")
                        time.sleep(5)
                        continue
                    content_str = raw_json.get("choices", [{}])[0].get("message", {}).get("content")
                    cleaned_content_str = clean_json_response(content_str)
                    return json.loads(cleaned_content_str)
                except:
                    tqdm.write(f"  [Error] 无法解析 JSON (尝试 {attempt + 1})")
                    time.sleep(5)
                    continue

            # 如果直接返回的就是结果（有些非OpenAI接口行为不同），尝试直接返回
            if "evidence_groups" in response_json:
                return response_json
            
            # 标准 OpenAI 格式处理
            if "choices" in response_json:
                content_str = response_json["choices"][0]["message"]["content"]
                cleaned_content_str = clean_json_response(content_str)
                return json.loads(cleaned_content_str)
                
            return None

        except Exception as e:
            tqdm.write(f"  [Exception] {e}")
            time.sleep(5)

    return None

def main():
    if not API_KEY:
        raise RuntimeError("Missing ACMMM_JUDGE_API_KEY for L2 evidence mining.")
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        
    all_files = glob.glob(os.path.join(INPUT_DIR, "*.json"))
    if not all_files:
        print(f"输入文件夹 {INPUT_DIR} 为空！")
        return

    # 过滤已处理文件
    files_to_process = []
    for f in all_files:
        base_name = os.path.basename(f)
        output_path = os.path.join(OUTPUT_DIR, base_name)
        if not os.path.exists(output_path):
            files_to_process.append(f)
            
    print(f"=== L2 任务启动 ===")
    print(f"总文件: {len(all_files)}, 待处理: {len(files_to_process)}")

    progress_bar = tqdm(files_to_process, desc="Mining L2", unit="file")
    
    for file_path in progress_bar:
        file_name = os.path.basename(file_path)
        progress_bar.set_description(f"Proc: {file_name}")
        
        full_text, id_map = parse_meeting_json(file_path)
        if not full_text:
            continue
            
        result = get_evidence_from_api(full_text, file_name)
        
        if result and "evidence_groups" in result:
            output_path = os.path.join(OUTPUT_DIR, file_name)
            
            final_data = {"source_file": file_name, "evidence_groups": []}
            for group in result["evidence_groups"]:
                ids = group.get("ids", [])
                # 校验 ID 是否存在
                valid_ids = [i for i in ids if i in id_map]
                if valid_ids:
                    group["ids"] = valid_ids
                    # 补充原文方便人工查看
                    group["original_text"] = [id_map[i].split(": ", 1)[-1] for i in valid_ids if i in id_map] # 只取文本部分
                    final_data["evidence_groups"].append(group)

            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(final_data, f, ensure_ascii=False, indent=2)
        else:
            tqdm.write(f"  [Failed] {file_name} 无有效结果")

if __name__ == '__main__':
    main()
