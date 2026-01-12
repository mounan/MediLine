import os
import json
import pandas as pd
from src.data_fetcher import fetch_real_data
from src.logic_core import RegistrationTrialExtractor

# 配置
FETCH_LIMIT = 100
QUERY_TERM = "Non-small cell lung cancer"  # 你可以修改为你需要的疾病关键词
OUTPUT_DIR = "data"
OUTPUT_FILE = "qualified_trials.json"


def main():
    print(f"🚀 开始执行批处理任务...")
    print(f"📂 目标输出目录: {OUTPUT_DIR}/")

    # 1. 确保输出目录存在
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 2. 获取数据
    print(f"📡 正在从 API 获取 {FETCH_LIMIT} 条关于 '{QUERY_TERM}' 的数据...")
    raw_df = fetch_real_data(limit=FETCH_LIMIT, query_term=QUERY_TERM)

    if raw_df.empty:
        print("⚠️ 未获取到数据，请检查网络或关键词。")
        return

    print(f"✅ 成功获取 {len(raw_df)} 条原始数据。")

    # 3. 运行 AI 筛选逻辑
    print("🧠 正在运行筛选逻辑 (Logic Core v2.0)... 这可能需要一点时间。")
    extractor = RegistrationTrialExtractor()

    # process 方法内部会自动处理异步循环
    processed_df = extractor.process(raw_df)

    # 4. 筛选合格数据 (保留 Priority 和 Kept)
    # 根据 app.py 的逻辑，合格状态为 "🔥 Priority" 和 "✅ Kept"
    qualified_df = processed_df[processed_df['ui_status'].isin(
        ["🔥 Priority", "✅ Kept"])]

    # 5. 保存结果
    output_path = os.path.join(OUTPUT_DIR, OUTPUT_FILE)

    # 转换为字典列表以便保存为 JSON
    records = qualified_df.to_dict(orient='records')

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(records, f, indent=4, ensure_ascii=False)

    # 6. 打印统计信息
    print("-" * 30)
    print(f"🎉 处理完成！")
    print(f"📊 统计报告:")
    print(f"   - 原始获取: {len(raw_df)}")
    print(f"   - ❌ 拒绝/噪声: {len(processed_df) - len(qualified_df)}")
    print(f"   - ✅ 最终合格: {len(qualified_df)}")
    print(f"💾 文件已保存至: {output_path}")


if __name__ == "__main__":
    main()
