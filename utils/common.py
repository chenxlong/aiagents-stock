"""
工具函数
"""

import re


#"【推理过程开始】\n{message.reasoning_content}\n【推理过程结束】\nXXXXX"
def split_thinking_and_result_content(text: str) -> tuple[str, str]:
    """
    从文本中提取推理过程内容和分析结果内容
    
    Args:
        text: 包含推理过程的文本
    
    Returns:
        推理过程内容和分析结果内容，分别作为元组的元素返回
    """
    pattern = r"【推理过程开始】\s*(.*?)\s*【推理过程结束】\s*(.*)"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    else:
        return "", text.strip()
    

if __name__ == "__main__":
    tests = [
        "【推理过程开始】\n这是一个推理过程\n【推理过程结束】\n这是一个分析结果",
        "【推理过程开始】\n推理内容1\n推理内容2\n【推理过程结束】\n分析结果1\n分析结果2",
        "【推理过程开始】推理内容【推理过程结束】分析结果",
        "【推理过程开始】\n  带空格的推理过程  \n【推理过程结束】\n  带空格的分析结果  ",
        "【推理过程开始】\n\n推理内容\n\n【推理过程结束】\n\n分析结果\n\n",
        "API返回空响应",
        "【推理过程开始】\n\n推理内容\n\n【推理过程结束】\n"
    ]
    
    for i, text in enumerate(tests, 1):
        print(f"\n测试用例 {i}:")
        thinking, content = split_thinking_and_result_content(text)
        print(f"推理过程: [{thinking}]")
        print(f"分析结果: [{content}]")