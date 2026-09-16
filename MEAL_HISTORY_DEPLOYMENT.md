# 餐食实拍与历史记录

## 业务边界

- 健康岛和营养配餐增加历史入口；总务另有按周实拍上传入口。
- Excel 菜单发布仍走现有解析、核对、发布流程，菜单图改为可选；实拍可晚几周补传。
- 每校区、学期、周次一张当前汇总图；再次上传创建版本，不覆盖旧文件。
- 家长仅看绑定学生稳定 UserID 的明细，班主任仅看本学期本班，总务/管理员看本校区。
- 无法核对历史身份的行不会匹配给家长；往学期班主任明细需联系总务。
- 截止快照独立保存名单、选择、供餐日期和结构化菜单。停餐日不计数，周末按已发布供餐日处理。
- 本部/宝林继续沿用原默认 A 补选；罗泾只归档现有选择，不额外补选。
- 初次回填标记 backfill，不能恢复此前已删除或覆盖的数据。实时数据变动会提示核对，人工修正版需原因及版本检查。
- 实拍图片及归档是按同一校区、学期、周次关联，并不是把每张照片关联到某个学生。

## 数据与文件

各校区原业务 SQLite 中只新增 `meal_history_settings`、`meal_week_archives`、
`meal_week_archive_choices`、`meal_week_photos` 表及一个索引。迁移不修改原菜单、选餐、名册或认证表。

图片文件位于 `uploads/meal-photos/{campus}/{semester}/weekNN/`，随机 ID 文件名。
清理 EXIF、转正后的 JPEG 原尺寸图和预览图分别存储，数据库只保存路径和元数据。
最大 20MB / 2400 万像素，Linux 文件锁确保全体 worker 同时仅解码一张图片。
照片不自动删除；备份需同时覆盖上述目录和三份业务数据库。按磁盘实际增长定期检查，不以数据库备份代替照片备份。

## 部署步骤

1. 在隔离副本安装 `requirements-meal-history.txt` 并运行下述测试；核对生产 HEAD 和相关文件无其他改动。
2. 使用 `server/backup_meal_history.py --root <项目> --destination <站外新备份目录>` 获取三份一致性备份，并备份改动文件和 Nginx 配置。备份不可放进公开网站目录。
3. 运行 `server/migrate_meal_history.py --root <项目> --semester 2026s1` 只读预演，检查周次与供餐警告。
4. 安装 Pillow 依赖；暂时停止 `baoshan-meal-finalize.timer`，保持主服务运行。
5. 部署本次明确列出的代码文件，执行迁移命令加 `--apply`。只增表和归档记录，不覆盖数据库文件。
6. Nginx 增加 `internal /_meal_photos/` 指向照片目录；阻断 `/uploads/meal-photos/`。
   对 `/api/meal-photos/` 的反向代理设置 `X-Meal-Photo-Delivery: nginx`；应用仅接受回环代理发来的此标记。
   对 `/api/meal-history/` 设置 21MB 请求上限并开启请求缓冲。执行 `nginx -t` 后 reload。
7. 向 Gunicorn 主进程发送 HUP，保持 8 worker 与原 request/timeout 配置不变。
8. 恢复原定时器，验证新 worker、公开页面、未登录 API 拒绝、图片目录拒绝及只读数据查询。

## 测试

```bash
python -m unittest discover -s tests -p test_meal_history.py -q
python -m unittest discover -s tests -p test_menu_excel_import.py -q
python -m unittest discover -s tests -p test_meal_pending.py -q
```

浏览器模拟测试：安装了 Playwright / Edge 的环境执行 `node tests/meal_history_browser.cjs`。
该测试使用虚构数据，不连接生产 API。手机实机钉钉上传、图片预览和下载仍需老师验收。

原始生产基线的 `test_meal_nutrition_auth.py` 在本机有 21 个失败（共 52 项），主要涉及旧名册夹具和社团规则；本次分支与基线相同，未声称全仓测试通过。

## 回滚和后续维护

- 应用异常时恢复本次改动的旧代码文件并 HUP，恢复 Nginx 备份后检查并 reload；恢复定时器。
- 不用备份数据库整体覆盖实时数据库，否则可能丢失上线后的真实业务数据。
- 新增归档表和图片保留即可，不必为了回滚删库删表。Pillow 新增依赖可以保留。
- 学期标识如 `2026s1` 代表 2026—2027 学年第一学期。当前实时菜单没有学期列，因此新学期发布会被拦截，必须另行核对旧周归档与实时菜单清理流程；不得直接修改设置绕过校验。
- 本次不包含自动识别法定节假日、自动拼图、照片逐日分类、存量错餐批量修改、账号/社团改动或云存储采购。
