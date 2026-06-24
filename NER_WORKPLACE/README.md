# 明实录目标蒸馏 NER 工作台

本项目按 `Codex_Plan_明实录蒸馏NER工作台.md` 搭建，是一个本地单机 Web 应用：FastAPI 后端、SQLite 持久化、无构建步骤前端。目标流程是清洗语料、定义实体、设计 Prompt、LLM 批量标注、人工校对、构建训练数据、训练模型、结果展示与导出。

## 启动

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

浏览器打开 `http://127.0.0.1:8765`。如不想自动打开浏览器：

```powershell
.\.venv\Scripts\python.exe run.py --no-open
```

## 当前交付范围

- Phase 0：FastAPI、SQLite 全表初始化、九页前端壳、运行脚本。
- Phase 1：OpenAI 兼容 `base_url + api_key + model_name` 设置、掩码读取、测试连接、重试/限速/并发 client。
- Phase 2：txt 上传、清洗、繁简转换、按 `卷之X` 和 `○` 切条、降级句读、分句、分层抽样与统计。
- Phase 3：实体类型 CRUD、默认 PER/LOC/OFF、Prompt 模板保存、schema 注入、messages 预览、dry-run。
- Phase 4：LLM 批量标注后台任务、`llm_calls` 断点、JSON 解析、span 定位、重叠消解、进度查询。
- Phase 5：人工校对页，支持新增、确认、删除实体与句子确认。
- Phase 6：训练数据 JSONL 与 BIOES JSONL 构建、统计、导出路径；训练任务当前为可替换的模拟实现。
- Phase 7：标注浏览、词表式推理预览、指标展示、导出入口。

## 目录

```text
backend/      FastAPI、SQLAlchemy、服务与路由
frontend/     原生 ES Module 单页 UI，无 Node 构建
config/       默认配置与本机 secrets.json
data/         SQLite、语料、数据集、模型输出
run.py        一键启动
```

## 密钥

LLM API key 保存在 `config/secrets.json`，已加入 `.gitignore`。接口读取设置时只返回掩码，不返回明文 key。

## 训练说明

为保证端到端流程能在普通本机先跑通，`backend/services/trainer.py` 默认使用模拟训练任务生成进度、指标和 checkpoint 目录。后续可在该文件中接入真实 HuggingFace `transformers` token-classification 训练逻辑，REST/UI 契约无需改变。

如要安装真实训练依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-train.txt
```

## 导出格式

`/api/dataset/build` 会生成：

- `data/datasets/<name>/annotations.jsonl`
- `data/datasets/<name>/bioes.jsonl`

标注 JSONL 的实体对象包含 `linked: null`，为下游 CBDB 实体链接预留。
