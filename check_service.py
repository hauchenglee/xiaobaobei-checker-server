import re
import pycorrector
import torch
import kenlm
from autocorrect import Speller
import ssl
import os
import json
import anthropic

ssl._create_default_https_context = ssl._create_unverified_context


class CheckService:
    def __init__(self):
        # https://deepspeech.bj.bcebos.com/zh_lm/zh_giga.no_cna_cmn.prune01244.klm 下载了
        # self.klm_path = './models/zh_giga.no_cna_cmn.prune01244.klm'
        self.klm_path = '/opt/models/zh_giga.no_cna_cmn.prune01244.klm'

        if not os.path.exists(self.klm_path):
            raise RuntimeError(f"Model file not found at: {self.klm_path}")

        try:
            self.cn_corrector = pycorrector.Corrector(language_model_path=self.klm_path)
            self.spell = Speller(lang='en')
            self.en_corrector = pycorrector.EnSpellCorrector()
            print(f"Successfully initialized Chinese corrector with model at {self.klm_path}")
        except Exception as e:
            print(f"Error initializing Chinese corrector: {str(e)}")
            raise

        # 增加 debug 输出
        print("Pycorrector version:", pycorrector.__version__)

    def ai_service(self, data):

        prompt = '''
You are a Traditional Chinese text proofreading expert. Check for incorrect or misused characters based on standard Traditional Chinese usage.

Key checking points:
1. Wrong characters (e.g., "勞餒" instead of "煩惱")
2. Incorrect character combinations (e.g., "食腳踏車" instead of "騎腳踏車")
3. Commonly confused characters (e.g., "原則尚" instead of "原則上")

Do NOT check for:
- Grammar issues
- Semantic meaning
- Style preferences
- Punctuation

Examples of what to check:
✓ "食腳踏車" → "騎腳踏車" (wrong character usage)
✓ "原則尚" → "原則上" (wrong character)
✗ "我很快樂開心" (don't check redundant meaning)
✗ "他去學校" vs "他往學校去" (don't check grammar structure)

Position calculation rules:
1. Start counting from 0
2. Each character (including punctuation) counts as one position
3. Must return the exact position of the incorrect character in the original text

For example, in the text: "手雞". If "雞" is incorrect, its position should be 1

Additionally, prioritize corrections based on the user-defined terms provided. If a character sequence matches a user-defined term but may have alternative usages in other contexts, still prioritize the user-defined correction.

Please output in JSON format, including all found incorrect characters. For each error, include: original text, corrected text, and position. Focus only on clear character errors, avoid over-correction.

The Input JSON Schema:

```json
{
  "type": "object",
  "properties": {
    "article": {
      "type": "string",
      "description": "需要检查错字的文章内容，必须为繁体中文"
    },
    "terms": {
      "type": "array",
      "items": {
        "type": "string",
        "description": "用户自定义的词库，用于优先修正"
      }
    },
    "is_ai": {
      "type": "boolean",
      "description": "其他系统需要的参数，无需理会"
    }
  },
  "required": [
    "article",
    "terms",
    "is_ai"
  ],
  "additionalProperties": false
}
```

The input json example:

```json
{
  "article": "如果您是設計並居住在台北市的低收入戶，可以申請育兒津鐵，如果有身心障礙證明更好。",
  "terms": [
    "低收入戶",
    "中低收入戶",
    "身心障礙證明",
    "身心障礙者生活補助",
    "育兒津貼",
    "托育補助",
    "人籍合一",
    "設籍並居住"
  ],
  "is_ai": false
}
```

The output JSON Schema:

```json
{
  "type": "object",
  "properties": {
    "errors": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "original": {
            "type": "string",
            "description": "原始的错误文字"
          },
          "correction": {
            "type": "string",
            "description": "修正后的正确文字"
          },
          "position": {
            "type": "integer",
            "description": "错误文字在原文中的起始位置（从0开始）"
          }
        },
        "additionalProperties": false
      }
    }
  },
  "additionalProperties": false
}
```

The Output Jsom example:

```json
{
{
  "errors": [
    {
      "correction": "設籍並居住",
      "original": "設計並居住",
      "position": 4,
      "type": "term_mismatch"
    },
    {
      "correction": "中低收入戶",
      "original": "的低收入戶",
      "position": 13,
      "type": "term_mismatch"
    },
    {
      "correction": "育兒津貼",
      "original": "育兒津鐵",
      "position": 23,
      "type": "term_mismatch"
    }
  ]
}
```

You must strictly adhere to the output JSON schema when returning the response.

The actual input content:

''' + f"{data}"

        client = anthropic.Anthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY")
        )
        message = client.messages.create(
            model="claude-3-5-sonnet-20240620",
            max_tokens=1024,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        print("ANTHROPIC_API_KEY: " + os.environ.get("ANTHROPIC_API_KEY"))
        print("claude-3-5-sonnet-20240620 message: ")
        print(message)

        # 解析JSON
        data = json.loads(message.content[0].text)

        # 提取errors列表
        errors = data['errors']
        print("errors: ")
        print(errors)

        return errors

    def check_chinese(self, text):
        try:
            errors = []

            # 繁体转简体
            text = pycorrector.traditional2simplified(text)

            # 使用 pycorrector 进行检查
            results = self.cn_corrector.correct(text)
            # 处理返回的错误信息
            if isinstance(results, dict) and 'errors' in results:
                for error in results['errors']:
                    # error 格式为 (wrong, right, position)
                    if len(error) >= 3:
                        wrong, right, pos = error
                        # 都转换成繁体保持一致
                        wrong = pycorrector.simplified2traditional(wrong)
                        right = pycorrector.simplified2traditional(right)
                        errors.append({
                            'original': wrong,
                            'correction': right,
                            'type': 'chinese_correction',
                            'position': pos
                        })

            return errors

        except Exception as e:
            print(f"Error in Chinese correction: {str(e)}")
            return []

    def check_terms(self, text, terms):
        errors = []

        # 将词条按长度降序排序，确保优先匹配较长的词条
        sorted_terms = sorted(terms, key=len, reverse=True)

        for term in sorted_terms:
            # 在文本中查找近似匹配
            for i in range(len(text)):
                if i + len(term) > len(text):
                    break

                text_slice = text[i:i + len(term)]
                if text_slice != term:
                    # 计算编辑距离或相似度
                    similar = False
                    diff_count = sum(1 for a, b in zip(text_slice, term) if a != b)

                    # 如果长度相同且只有一个字符不同，认为是可能的错误
                    if len(text_slice) == len(term) and diff_count == 1:
                        similar = True

                    if similar:
                        errors.append({
                            'original': text_slice,
                            'correction': term,
                            'type': 'term_mismatch',
                            'position': i
                        })

        return errors

    def process_data(self, data):
        print(data)
        article = data.get('article', '')
        terms = data.get('terms', [])
        is_ai = data.get('is_ai', False)
        print(f"is_ai: {is_ai}")

        if not article:
            return {
                "status": "error",
                "message": "文章内容不能为空",
                "errors": []
            }

        all_errors = []
        print("Processing data...")

        if is_ai:
            print("AI mode")
            errors = self.ai_service(data)
            all_errors.extend(errors)
        else:
            print("Human mode")
            # 1. 先进行术语检查
            term_errors = []  # 先初始化
            if terms:
                term_errors = self.check_terms(article, terms)
                all_errors.extend(term_errors)

            # 2. 创建术语检查已覆盖的位置范围
            covered_ranges = []
            for error in term_errors:
                pos = error['position']
                length = len(error['original'])
                covered_ranges.append((pos, pos + length))

            # 3. 中文错别字检查，但跳过已被术语检查覆盖的部分
            chinese_errors = self.check_chinese(article)
            for error in chinese_errors:
                pos = error['position']
                length = len(error['original'])

                # 检查这个位置是否已被术语检查覆盖
                is_covered = False
                for start, end in covered_ranges:
                    if pos >= start and pos < end:
                        is_covered = True
                        break

                if not is_covered:
                    all_errors.append(error)

            # 按位置排序错误
            all_errors.sort(key=lambda x: x['position'])

        # 生成修正后的文本
        corrected_text = article
        if all_errors:
            # 从后向前替换，避免位置偏移
            for error in reversed(all_errors):
                pos = error['position']
                original = error['original']
                correction = error['correction']
                corrected_text = (
                        corrected_text[:pos] +
                        correction +
                        corrected_text[pos + len(original):]
                )

        # 简体转繁体
        corrected_text = pycorrector.simplified2traditional(corrected_text)

        result = {
            "status": "success",
            "message": "检查完成",
            "original_text": article,
            "corrected_text": corrected_text,
            "errors": [
                {
                    "original": error['original'],
                    "correction": error['correction'],
                    "position": error['position']
                } for error in all_errors
            ]
        }

        return result
