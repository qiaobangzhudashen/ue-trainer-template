# UE 单机修改器通用参考（UE4SS + CE → 单 UI 一体机）

> 面向新游戏、新功能的通用工作流。新会话开工只需要三样：本文件 + 游戏路径 + 你的需求。
> 本文档只保留跨游戏可复用的方法论；具体类名、签名、AOB、补丁位、ID 和已验证行为，放入该游戏自己的 `MOD-MEMORY.md`。
>
> 经验来源：UE5 单机《山门与幻境》（UE 5.7.4、RE-UE4SS 3.0.1-experimental）。该案例用于说明分工与坑，不是可照搬的参数表。

## 0. 核心原则

1. **证据优先**：先扫目录、dump 和日志再判断；不把上一个游戏的结论当答案。
2. **先读再改**：读原生参数/当前值，算好差值再写。**写之前先读，改最小字段，写完验证。**
3. **最短路径优先**（效率铁律）：先复现用户可见的那道门（按钮/弹窗/提示），找到门后**最近的一个判断**，最小补丁验证。不要先建通用免费层再到处补——两个跳转几分钟能成的事，不值得搭一套接口再返工。
4. **分层施工**：逻辑层走 UE4SS Lua（发奖/属性/hook 检查返回值，安全可逆）；native 层（扣除/计时/消耗/跳转）走内存补丁。各管各，互不抢。
5. **官方链优先**：游戏自己怎么发奖、升级、结算，就走哪条链，参数照官方语义传。
6. **运行时事实优先于静态猜测**：ObjectDump 只给候选，进游戏实测才算数。
7. **通用与项目事实分离**：删掉游戏名称后仍成立的放本文档；必须填具体名称、数值、签名、AOB 的放 `MOD-MEMORY.md`。

---

## 1. 新游戏开工主流程

1. **静态侦察**：找游戏 EXE、`Content/Paks/*.pak`、`Engine/` 目录；引擎版本从崩溃报告（`Saved/Crashes/CrashContext.runtime-xml`，`++UE5+Release-x.y`）或 EXE 内版本串确认。
2. **装 UE4SS**：版本必须覆盖目标引擎（老版扫不出 GUObjectArray 就换 experimental 新构建）；`EngineVersionOverride` 留空自动识别；**关闭自动热重载**，只用手动 Ctrl+R（自动重载已实锤导致崩溃）；但部署/补齐时必须把 `EnableHotReloadSystem` 置 `1`（自带包默认 `0`，此时 Ctrl+R 全局无反应）。
3. **确认启动**：Steam 是否必须运行、启动后注入是否成功（示例：`dwmapi.dll` 代理）、`ue4ss/UE4SS.log` 有无报错。
4. **确认输入**：游戏内控制台开启方式（示例：`~`/F10）、Ctrl+R 重载、热键位；输出双通道（控制台回显 + `UE4SS.log`）。
5. **全对象导出**：拿 `UE4SS_ObjectDump.txt`，之后一切逆向都从搜它开始。
6. **目标系统六问**（第 2 节）：物品/属性/商店/科技/拍卖/建筑，未完成不写业务代码。
7. **最小用例**：一次只读一个数、改一个字段、读回 + 看游戏内 UI；成了再批量、再上 UI。
8. **归档**：结论进 `MOD-MEMORY.md`（按第 7 节模板）。

新会话开工时先填完下面 5 行（对应模板见 [`MOD-MEMORY.template.md`](MOD-MEMORY.template.md)，缺项补项，不靠回忆）：游戏根目录 / 需求原文 / 引擎版本证据 / 双通道状态 / 最小用例计划。

### 1.1 双通道就绪检查（UE 必须 UE4SS+内存两条都通）

- Lua 通道：脚本部署后游戏内 Ctrl+R，看到 `loaded` 回显（控制台 + `UE4SS.log` 各一行）；hook 类以日志成功行为准（如免费开关的两行 ids），重载/重启后重开。**本局启动时 Mod 未注册则本局注定无通道，Ctrl+R 救不回，必须重启游戏**（见 1.2 顺序铁律）。
- 内存通道：CE 桥脚本放 `autorun` 自启（或确认管道能 ping 通）；直连游戏进程确认 PID；抽查已有 AOB 是否仍唯一（1 分钟，版本漂移第一发现人）。
- 开关归属：同一批字节，UI 和 CE 表**二选一**操作，反向互顶必出灵异问题。

### 1.2 部署与热重载纪律
- 双注册（experimental 3.x 真认的是 `Mods/mods.json`，`mods.txt` 只是 load order）：两边都要有 `<Name>`，缺一边即静默跳过——日志表现为到 `Keybinds` 就 `Event loop start`，无报错、无 `loaded`、无 `Error loading`。`mods.txt` 必须干净无空行无注释行；每次解包/更新 UE4SS 后重验两边。
- 改完脚本部署后游戏内 **Ctrl+R 一次**，看到 `loaded` 回显才算数；按之前先关游戏内控制台、游戏窗口聚焦，否则按键被输入框吃掉。
- **顺序铁律：先开修改器（补本体 + 双注册 + Scripts），再开游戏。** 启动瞬间注册表就必须就位；新用户/Steam 更新后首次必须走这个顺序。
- 修改器启动自动体检三件套（缺一不可，进 `engine/deploy.py` 复用）：①校验注入本体（代理 dll + `ue4ss/` 目录，缺即用自带 zip 补，zip 打进 exe，只补缺项）②双注册修复 + `EnableHotReloadSystem=1` ③发通道探针（如下发 `lv_help` 等 `exec done`，超时判死）。补完本体必须提示**重启一次游戏**，不要在本局继续测。
- **hook 是纯内存的**：重载/重启即失效，用前重开（如免费开关），以日志回显为准，不要凭记忆。
- 外部 UI 下发命令走桥接文件：写 `.tmp` 再整体替换成 `cmd.txt`（防读半截），游戏内 `LoopAsync` 轮询执行，结果只回 `UE4SS.log`（`[LVT]` 前缀），执行后文件清空。
- `启动修改器UI.bat` 必须纯 ASCII（中文路径/命令会碎）。

### 1.3 工程目录约定（一游戏一文件夹）

- 每个游戏一个工程根目录：下载的工具（UE4SS 包、CE 桥）、制作的源码（`Scripts/`、UI、内存层）、`dumps/`、`*.CT`、ID 对照表、`MOD-MEMORY.md` 全在里面，不散落。
- 新会话用户只报工程根目录，agent 不再全盘搜索；续活时路直接续，不重找。
- 通用文档放 `D:\skills\ue-trainer\`，游戏私货不出工程目录；第三方原包保留版本号命名，删了就把下载地址记进第 7 节。

---

## 2. 通用侦察框架：目标系统六问（UE 版）

| # | 问题 | 必须记录 |
|---|---|---|
| 1 | **谁承载它？** | 类全名（`/Script/Game.Module:Class`）、实例入口（`FindFirstOf` 常驻？场景限定？）、字段全集 |
| 2 | **有哪些维度？** | 枚举全名+值、品质/境界/称号档位、ID 与中文名映射来源（运行时表拿不到就烘焙） |
| 3 | **怎么读？** | 完整签名、返回值语义（注意同一数值可能多口径并存，验证时注明用哪个） |
| 4 | **怎么写？** | 增量还是绝对值；struct 参数是高压线（读可写不可，传参 round-trip 会崩） |
| 5 | **写完怎么生效？** | 官方刷新调用、UI 重算时机（战斗面板会被重算刷回，不要直写衍生值） |
| 6 | **官方如何产出？** | 发奖/升级/结算/刷新调用链和参数组合 |

### 2.1 多口径陷阱（必查，易错）

同一数值常有多种读法并存（示例：UI 显示的 int 口径 vs 内存 Map 存的 float 口径）。门后判断走哪条，以实测为准；验证时注明口径；补丁要能覆盖实际走的那条，不要默认只改一条。

### 2.2 按类目寻找参照（已验证行；新类目按六问现填，不要预设流程相同）

| 类目 | 首要侦察对象 | 官方参照 |
|---|---|---|
| 物品/货币 | 背包组件、资源 Map、发奖链 | 官方发奖/拾取/商店购买 |
| 属性/弟子 | actor + 内嵌 struct + 加成字段；战斗面板重算规则 | 修炼/突破/授职官方入口 |
| 商店 | 商品数组、购买函数（先只读商品再小额试买） | 商店购买 |
| 科技 | 状态枚举、队列/加速函数；直设点亮可能是空心的 | 研究材料+手动研究 |
| 拍卖 | 组件计时字段、Skip/Exit 语义（先只读计时，再动） | NPC 上拍周期 |
| 建筑 | 等级字段、升级零参入口（先读等级再试升） | 升级/建造 |

### 2.3 跨类目必查

- 对象是否只在特定场景存在（主菜单/城镇/战斗各一套，不要跨场景解引用）。
- `FindObject` 按路径找 DataTable 大概率失败，表靠枚举匹配；运行时拿不到的表走烘焙。
- 改存档与实时修改互斥：改存档关游戏，实时改读档进场景。

---

## 3. 动手规范：Lua 与 CE 分工

### 3.1 UE4SS Lua（逻辑层）

- 调函数 `obj:Func(args)`，读 `obj.Prop`，写 `obj.Prop = v`；找对象 `FindFirstOf`/`StaticFindObject`/`UEHelpers`。
- hook 改返回值：`RegisterHook(全路径, function(self, ...) return <值> end)`，注销要干净；先拿无风险函数做 A/B 验证（hook 时变、注销恢复），再挂真目标。
- hook 拦不住 `void`（如实际扣除）和 native 内部直读——这些归 CE。
- 外部命令桥（推荐脚手架，非 UE4SS 自带）：游戏内 `LoopAsync` 轮询 `cmd.txt`，外部写 `.tmp` 再整体替换；结果回日志 `[LVT]` 前缀；命令注册 `reg(name, fn)` + 控制台 `lv_` 双入口共用实现。
- 批量发奖/刷屏类操作先小批量试，再全量；功法秘籍类常有单品上限，小批量验证。
- 验证用**秒级对照**（写后立刻读），分钟级对照会被生产 tick 污染出假阳性。

**Hook 返回值语义（检查函数放行的唯一正确口径）：** 回调 `return` 非 nil 即覆盖原返回值，`return nil`/无 return 则保留原值；`/Script/` 开头路径支持 pre（第2参）+post（第3参），BP 路径只用第2参；delegate 不支持，被 hook 函数须已在内存；返回的 PreId/PostId 双 ID 注销。不要把“return true 放行”当通用模板——先确认目标函数返回值语义。
**读改入参：** hook 回调首参是 Context（this），余参按 UFunction 签名逐个包 `RemoteUnrealParam`，一律经 `get()` 读、`set()` 写，不猜内存布局。
**游戏线程封送：** 对象创建/调官方发奖包 `ExecuteInGameThread(fn)`（外部桥回调里直接调官方函数会崩）。
**场景限定对象：** `FindFirstOf` 拿不到的动态/场景对象用 `NotifyOnNewObject(类路径, fn)` 监听构造（含派生类），回 `true` 即单次注销。
**驱动三选一：** `cmd.txt` 文件桥（默认）/ `RegisterKeyBind` 游戏内热键（控制台聚焦才触发）/ `RegisterConsoleCommandHandler` 自定义控制台命令（回 `true` 截断）。验证=按热键/敲命令看日志。
**容器只调官方 API：** `TMap:Find/Add/Contains/Remove/Empty/ForEach`，`TArray` 1 基下标/`#arr`/`ForEach((i,elem))`（`elem:get()/set()`）/`Empty()`；只改已存在元素，批量先小量试。

### 3.2 CE（native 层）：搜→断→反→补丁

1. **搜**：拿用户可见的精确数（如某材料拥有量）做首扫，用官方发奖加一笔做收窄（几百→1，常一步到位）；0 值不搜。
2. **断**：硬件读/写断点埋上，让用户做触发动作（悬停/点击），读命中。
3. **反**：顺藤找比较+跳转（`cmp/test/comiss + jcc`）；**用户可见门后的第一个判断就是目标**，不要顺着藤摸出三里地。
4. **补丁**：nop/jmp 最小改；简单覆盖不了时（条件分支/寄存器保护/只对特定对象生效）用代码洞：原地写 E9 跳到申请的内存，执行完跳回（见 3.3 cave 约定）；载体统一 `aobscanmodule` 限定主模块（全局 `aobscan` 卡 UI 约 10 秒）；**特征码不得包含补丁位自身**（否则打上补丁后自己搜不到自己）。
5. **成对意识**：检查放行后，扣除侧变负会走它自己的不足分支——检查与扣除补丁成对出现，一开全开。
6. **Mono 符号只做开发期定位**：Unity 游戏（IL2CPP/Mono）在 CE 里可用 Mono 方法名+偏移（`LaunchMonoDataCollector` + `Class.Method+偏移`）快速定位，但那是 JIT 地址，每次会变；成品一律转成所在模块（常为 `GameAssembly.dll`）上的 AOB，按普通补丁走。迁移链：Mono 定位 → 同版本空白工程 PDB 在 x64dbg 提特征 → 目标游戏验证 → 落 AOB（`game.yaml` 不留悬空 TODO）。

### 3.2b 搜不到数时的兜底路线（按顺序试）

1. **未知初值/浮点/指针**：unknown 初扫 + 变动/不变/增加/减少收窄；浮点改类型重扫；疑似指针走 pointer scan（偏移链表达，版本漂移后 rescan 按“特定偏移结尾”过滤）。
2. **无可见数值埋不了断点**（timer/结算类）：Ultimap/CodeFilter 记分支，以“门事件发生/未发生”两次过滤收敛热点；或 break-and-trace + 栈回溯，对比正常 vs 修改后执行流。已可一键执行：`ce lbr op=start`→做动作→`op=read`看分支对（往前找调用），`ce step thread=<id> count=80`逐条看`[CRYPTO?]`（往后找解密），完事`ce dbgdetach`。
3. **写指令被多对象复用**：看“这段代码访问了哪些地址”，用不同对象地址区分玩家/敌人/共享逻辑，顺藤找结构体基址；敌我字段用 dissect data 分组对比（组内同、组间异列即阵营字段）。
4. **命中点是通用函数**：dissect code 画调用/引用图，门判断常是其上游唯一 jcc，向上找调用方分流。
5. **Unity Mono**：Mono dissect 直接浏览托管类/方法并强制 JIT 出 native 地址，再转 AOB（跳过盲搜）。
6. **版本漂移保命**：AA 一律用注入模板（Template→Code/Full injection，64 位远跳按 Ctrl 生成）；`assert` 校验补丁前缀、`readMem` 快照原字节；CE 侧开 speedhack 降速冻结计时类逻辑争取扫描反应时间。

### 3.3 成品内存层（去 CE 化，单 exe 的关键）

- CE 只在开发期用；成品用 `pymem` 直连（`pip install pymem`；前提：单机无反作弊，`OpenProcess` 即够，无需驱动；有反作弊/驱动保护的游戏本路线不适用，另议）。
- `pymem.pattern.pattern_scan_module` 的 pattern 要 `re.escape`（它按正则跑）；`process_from_name` 返回对象，取 `.th32ProcessID`；64 位 Python 对 64 位目标。
- 开关语义：apply 打补丁+读回校验，restore 原字节写回；地址按 PID 缓存，进程重启自动重搜；游戏未运行按已关处理。
- UI 一个勾 = Lua 命令 + 内存补丁联动，同开同关。
- **代码洞（cave）成品约定**：`overwrite_len>=5`（放得下 E9），原地 `E9->洞` + nop 垫平；洞布局为 `[洞逻辑][E9跳回原址+overwrite_len][数据区]`，申请一次、释放一次（`VirtualAllocEx`/`VirtualFreeEx`，内存自带清零）；洞内分支（jne/je）组装时一次算好相对偏移，只出一个尾出口，不中途跳回；CE 里 `alloc(name,$8)+registersymbol` 的外部变量对应 `data_size` 声明 + 洞内 `0xAAAAAAAAAAAAAAAA` 占位回填（倍数/指针写数据区）。
- **组装链**：CE 调通的汇编经 keystone 出 hex、capstone 反汇编复核（栈平衡、标志位、分支落点）后再入库；不要手算偏移。
- **一致性校验**：入库前核对 ENABLE 的 label、DISABLE 回填字节、AOB 三者指向同一位置（label 复制错位是常见坏补丁源）。
- Unity IL2CPP 游戏内存层同样适用本节，模块名换成 `GameAssembly.dll` 即可；Lua 桥部分仅 UE4SS 有效，Unity 游戏只用内存层 + Mono 桥（另议）。

---

## 4. 一体机 UI 约定（单窗口、开关式、关闭即恢复）

1. 顶部：游戏根目录 + 部署按钮 + 游戏/Mod 状态自检。
2. Tab 按系统分（物品/常用包/弟子/建筑/拍卖…），数值页遵循读基线→输期望→算差值→写→重读。
3. 危险操作（全量发放、删特性、升级建筑）先确认框；不可逆标注清楚。
4. 日志框只收 `[LVT]` 提纯行 + 内存层 `OK/失败` 行；超时明确写“去游戏内/日志确认”，不谎报成功。
5. 新功能只增按钮和方法，不改无关页；中文名缺口（FText 无表）先标“待拆包”，不硬编。

---

## 5. 验证、排障与回滚

### 5.1 最小验证清单

- [ ] Ctrl+R 后有 `loaded` 回显；hook 类以日志两行成功为准
- [ ] 读数与游戏内面板一致（注明 int/float 口径）
- [ ] 写后立刻重读；UI 以“确认框能执行”为准，残留的红色缺货显示可能是旧账单渲染，不等于失败（见 5.2 旧账单行）
- [ ] 存档+读档正常（坏数据会在存档序列化时崩）
- [ ] 开关关闭后字节/行为恢复；只走一边开关
- [ ] 重复操作不叠加；场景切换后仍有效

### 5.2 常见症状速查

| 症状 | 可能原因 | 下一步 |
|---|---|---|
| 改了没效果 | 没 Ctrl+R；hook 本局没开；补丁字节不在内存 | 查 `loaded` 回显、hook 日志行、直读补丁位字节 |
| 升级/购买仍报缺 | UI 用的是面板打开时算好的旧账单；或执行侧扣除变负 | 先确认 Lua hook 开着；检查+扣除成对 patch；看确认框按钮状态不要只看红字 |
| 调了 native 函数后 UI 卡死 | 踹到状态机奇怪分支（如拍卖 Skip） | 列禁用名单；重读档恢复，卡住时不存档 |
| struct 一碰就崩 | 装备/资源 struct 双向转换不支持 | 只读 struct；走官方标量入口；装备走存档流程 |
| 秒级有效、几分钟后“失效” | 生产 tick 污染对照 | 缩短对照窗口；以 Map 读回为准 |
| 全局 AOB 勾选卡 10 秒 | `aobscan` 全内存扫 | 一律 `aobscanmodule` 限定主模块 |
| 打上补丁后重搜不到 | 特征码含补丁位 | 特征码只取补丁前前缀 |
| 6 字节短 AOB 新版本失效 | 正常损耗 | 重走搜→断→反→补丁，不要硬套旧码 |
| 游戏更新后全挂 | 基址/AOB/签名漂移 | 按第 1 节重走侦察，先验 AOB 唯一性 |
| 补丁开后重进/读档/切场景失效 | hook 纯内存 + 场景限定对象 | 重开 hook（以日志为准）；场景对象改 NotifyOnNewObject 监听 |
| CE 里搜到、成品搜不到 | 特征码含补丁位/模块名写错 | 特征码只取补丁前前缀；`module` 与 game.yaml 一致（UE 主模块/Unity GameAssembly.dll） |
| 敏感操作后崩溃有时无 dump | 非受控退出（如 Text 传参挂起线程） | 该类入口直接禁用，走存档流程 |

### 5.3 回滚

- Mod 回滚：`mods.txt` 置 0 + Ctrl+R；UE4SS 整包保留旧版备份。
- 内存补丁回滚 = restore 原字节；CT 回滚 = 取消勾选（会写回原字节，注意别和 UI 互顶）。
- 存档类操作前先备份存档；拿不重要的对象先测（如废档弟子）。

---

## 6. 项目记忆规范

每个游戏一个 `MOD-MEMORY.md`（见 [`MOD-MEMORY.template.md`](MOD-MEMORY.template.md)），至少记录：环境（路径/版本/引擎证据/UE4SS 版本）、启动与输入、生命周期与常驻入口、六问答案、已验证陷阱、补丁位（AOB/偏移/开字节/关字节/管线）、进度、部署与回滚。

判断规则：**删掉游戏名称后仍成立的放本文档；必须填具体名称、数值、签名、AOB、路径的放 `MOD-MEMORY.md`。**

---

## 7. 工具与参考

- [RE-UE4SS](https://github.com/UE4SS-RE/RE-UE4SS)：UE4SS 本体、发行版、Lua Mod 文档（`docs/`）、Issue 与版本适配说明。引擎版本不对就换 experimental 构建。
- [Cheat Engine 官网](https://www.cheatengine.org)：CE 本体下载。设置要求：Extra 里关掉 “Query memory region routines”（开着扫保护页会蓝屏）。
- [cheatengine-mcp-bridge](https://github.com/miscusi-peek/cheatengine-mcp-bridge)（已验证，v12）：Lua 桥（`MCP_Server/ce_mcp_bridge.lua`，放 CE `autorun` 自启）+ 管道直连；能力含扫值/AOB/反汇编/硬件断点/读写内存/AA 脚本/DBVM。`ce_direct.py` 式直连即可驱动，无需 MCP 客户端。
- 备选桥（同协议不同封装，按需换，不混用）：[ce-mcp](https://github.com/IMRX44/MCP)（`find_what_writes/accesses` 一键封装、HTTP 环回）、[cheat-engine-mcp](https://github.com/drdon1234/cheat-engine-mcp)（120 工具、AOB 注入模板）。
- `pip install pymem`（[PyPI](https://pypi.org/project/pymem/)）：成品内存层，64 位 Python 对 64 位目标。
- keystone-engine + capstone（制作期组装/复核 cave 用，运行时不需要）。
- PyInstaller：单 exe 打包（Python + pymem + tkinter），朋友双击即用，CE 只留开发侧。

以上工具只负责找证据或执行已验证的补丁，不能替代目标游戏内的实测。
