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
MODEL_NAME = os.getenv("ACMMM_L1_MODEL", "gpt-5")

# 路径配置
INPUT_DIR = os.getenv("MEETING_INPUT_DIR", "data/Real_meeting")
OUTPUT_DIR = os.getenv("EVIDENCE_OUTPUT_DIR_L1", "out/L1/Evidence")
LOG_FILE = os.getenv("EVIDENCE_LOG_FILE_L1", os.path.join(OUTPUT_DIR, "api_log_L1.jsonl"))

# === L1 JSON Schema ===
RESPONSE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "extract_l1_evidence",
        "schema": {
            "type": "object",
            "properties": {
                "evidence_groups": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "topic": {"type": "string", "description": "证据的主题，如'项目时间'"},
                            "ids": {"type": "array", "items": {"type": "integer"}, "description": "连续的句子ID列表"},
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
SYSTEM_PROMPT = """你是一个严格的会议数据质检员。
你的任务是从会议记录原文中提取【Level 1: 显性局部检索】的证据片段。

### Level 1 定义
- **所见即所得**：答案完全包含在一段连续的对话中，表述直白。
- **事实类信息**：重点关注具体时间、地点、数字（预算/人数）、人名、定义或罗列的清单。
- **形态约束**：证据必须是【单一句子】或【连续的 2-3 句话】。句子 ID 必须是连续的。

### 任务要求
1. 扫描全文，寻找高密度的“事实块”。
2. 提取这些句子的 ID。
3. 确保提取的信息在后文中**没有**被修改或推翻。
4. 请尽可能多地提取，至少提取 8-10 组以上的证据。
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
        raise RuntimeError("Missing ACMMM_JUDGE_API_KEY for L1 evidence mining.")
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
            
    print(f"=== L1 任务启动 ===")
    print(f"总文件: {len(all_files)}, 待处理: {len(files_to_process)}")

    progress_bar = tqdm(files_to_process, desc="Mining L1", unit="file")
    
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
