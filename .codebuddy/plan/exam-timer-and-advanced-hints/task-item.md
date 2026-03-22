# 实施计划

- [ ] 1. 修改服务端按级别设置差异化超时时间
   - 在 `server/main.py` 的 `/api/register` 接口中，根据 `data.exam_id` 设置不同的超时分钟数：v1=10、v2=20、v3=30
   - 将超时分钟数存入 `ExamSession`（需确认 `ExamSession` 模型是否有 `timeout_minutes` 字段，若无则新增）
   - 在 `/api/submit` 接口的超时检查处，将硬编码的 `timedelta(minutes=30)` 改为读取 session 中存储的超时分钟数
   - 将注册响应中 `expires_in_minutes` 字段的硬编码值 `30` 改为动态返回对应级别的分钟数
   - _需求：1.1、1.2、1.3、1.4、1.5_

- [ ] 2. 修改 `server/models.py` 为 `ExamSession` 新增超时字段
   - 在 `ExamSession` 数据模型中新增 `timeout_minutes: int = 30` 字段
   - 确认 `storage.py` 中 session 的序列化/反序列化逻辑能正确持久化该字段
   - _需求：1.1、1.2、1.3_

- [ ] 3. 修改三个试卷 Markdown 文件中的时间说明
   - 修改 `exam_papers/md/v1.md`：将考前须知第 4 条和注意事项中所有 `30 分钟` 改为 `10 分钟`
   - 修改 `exam_papers/md/v2.md`：将考前须知第 4 条和注意事项中所有 `45 分钟` 改为 `20 分钟`
   - 修改 `exam_papers/md/v3.md`：将考前须知第 4 条和注意事项中所有 `60 分钟` 改为 `30 分钟`
   - _需求：1.6_

- [ ] 4. 在 `v3.md` 考前须知中增加"主人需在旁盯守"的预防性提示
   - 在 `exam_papers/md/v3.md` 的考前须知列表中新增第 7 条（醒目警告）：说明高级考试涉及用户身份校验，需要主人全程在旁盯守，随时可能需要协助操作（如 GitHub 登录）
   - 在考前须知末尾的"请向用户确认"确认事项列表中，新增一条确认项：主人是否已知晓本次考试可能需要在旁协助，并同意全程陪同
   - _需求：2.1、2.2、2.4_

- [ ] 5. 在 `exam_papers/base.py` 的 `L3-4` 题目 instructions 中增加主人在旁提示
   - 在 `L3_TASKS` 中找到 `task_id="L3-4"` 的题目
   - 在其 `instructions` 字段开头（challenge_code 注入之前的静态文本部分）增加一段提示：该题目需要在 GitHub 上登录并发表评论，涉及账号身份校验，请确认主人在旁边，必要时由主人协助完成登录操作
   - _需求：2.3_
