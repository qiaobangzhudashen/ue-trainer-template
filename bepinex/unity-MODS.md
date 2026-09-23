# Unity BepInEx MOD 开发通用参考

> 面向新游戏、新功能的通用工作流。本文档只保留跨游戏可复用的方法论；具体类名、枚举、API 参数、路径和已验证行为，放入该游戏自己的 `MOD-MEMORY.md`。
>
> 经验来源：Boar Knight Demo（Unity 2022.3.62f3、IL2CPP、BepInEx 6）与侠影录（Unity 2022.3.60f1、Mono、BepInEx 5）。这两个案例用于说明差异，不是可直接照搬的参数表。

## 0. 核心原则

1. **证据优先**：先扫描目录、程序集和日志，再判断构型；不要把上一个游戏的结论当答案。
2. **先读再改**：先读取原生对象和参数语义，再决定写入方式。
3. **最小写入**：只修改目标字段；增量 API 必须计算差值，禁止把绝对值当增量传入。
4. **官方产出优先**：游戏自己如何掉落、打造、学习、交付或刷新，就是最可靠的合法参数参照。
5. **写后验证**：重新读取结果，并验证缓存、事件、UI、场景切换和重复操作。
6. **运行时事实优先于静态猜测**：反编译用于提出候选，最小插件和日志用于确认。
7. **通用规则与项目事实分离**：删掉游戏名称后仍成立的内容放本文档；必须填写具体名称或数值的内容放项目记忆。

---

## 1. 新游戏开工主流程

每个新游戏或新目标类目都重新走一遍，不要从旧项目复制结论。

1. **静态侦察**：找游戏 EXE、`*_Data`、`Managed`、`GameAssembly.dll`、`global-metadata.dat`、`BepInEx/core` 和 `BepInEx/interop`。
2. **构型判定**：输出 `Likely Mono`、`Likely IL2CPP` 或 `Unknown`，记录证据；不要仅凭一个文件绝对下结论。
3. **确认工程**：独立确认 BepInEx 分支、插件基类、TargetFramework、程序集引用来源和当前游戏版本。
4. **确认启动**：验证是否必须通过 Steam、启动器或特定参数启动，并确认 BepInEx 日志生成。
5. **确认输入与生命周期**：确认旧 Input、新 Input System、第三方输入库或混合方案；用最小探针确认 `Awake`、驱动入口和场景切换后的存活状态。
6. **完成目标系统六问**：见第 2 节。六问未完成前，不写业务修改代码。
7. **做最小用例**：只读一个对象、改一个字段、重新读取并确认 UI；成功后再做批量操作和复杂 UI。
8. **归档事实**：把本游戏的 API、补丁点、枚举、路径、快捷键、验证结果和踩坑写入 `MOD-MEMORY.md`。

建议每次新会话先复制并填写 [`GAME-SCOUT.template.md`](GAME-SCOUT.template.md)。

### 1.1 构型与版本判定

| 证据 | 结论 | 备注 |
|---|---|---|
| `*_Data/Managed/Assembly-CSharp.dll` 等程序集 | `Likely Mono` | 还要结合 BepInEx 运行时组件确认 |
| `GameAssembly.dll` + `global-metadata.dat` | `Likely IL2CPP` | 还要确认 interop 是否生成 |
| 只有 `UnityPlayer.dll` | 不足以判断 | 需要更多目录或运行时证据 |
| `BepInEx/interop` 存在 | 可能已生成 IL2CPP 互操作程序集 | 不代表版本一定匹配 |

**Mono/IL2CPP 与 BepInEx 5/6 不是严格一一对应关系。** 常见组合可以作为线索，但最终以目标游戏已安装的 BepInEx 分支、插件基类、官方模板和可运行引用为准。TargetFramework 也不能仅凭 Mono/IL2CPP 二选一决定。

### 1.2 启动方式

- 查游戏目录、Steam AppID、启动器和现有日志；直接运行 EXE 后立即退出时，先确认是否需要 Steam 启动。
- 记录实际启动命令、启动前置条件和日志位置。
- 确认 `BepInEx/LogOutput.log` 或游戏自己的 Unity 日志中出现插件 GUID。
- 不要把“退出码 0”直接等同于某一个原因；结合日志、Steam 校验和启动器行为确认。

### 1.3 输入系统

可能的输入来源包括：

- Unity Legacy Input；
- Unity Input System（通常可从 `Unity.InputSystem.dll`、类型或反编译引用确认）；
- Rewired、InControl 等第三方库；
- 游戏自己的输入管理器；
- 多套系统并存。

输入层应与业务层隔离，必要时提供适配器。`Input.GetKeyDown` 是否有效必须在目标游戏中实测；不要预设新 Input System 一定使旧 API 失效。绑定 MOD 快捷键前先检查游戏原有占用，并把最终键位记入项目记忆。

---

## 2. 通用侦察框架：目标系统六问

打开编译器前，先把要操作的对象看明白。目标可以是物品、装备、货币、属性、技能、任务、存档、战斗数值、商店、地图或外观。

| # | 问题 | 必须记录 |
|---|---|---|
| 1 | **谁承载它？** | 类、命名空间、字段/属性全集、实例入口、哪些字段不用 |
| 2 | **有哪些维度/档位？** | 枚举或 int、品级/颜色/强化等不同维度、名称和颜色来源、子类型与前置 |
| 3 | **怎么读？** | 完整签名、入口对象、返回值语义、对象是否已就绪 |
| 4 | **怎么写？** | 完整签名、参数含义、默认值、特殊语义、绝对值还是增量 |
| 5 | **写完怎么生效？** | 缓存重算、事件、UI 刷新、场景限制、是否需要再次读取 |
| 6 | **官方如何产出？** | 对应的掉落/打造/学习/交付/刷新流程、调用链和参数组合 |

### 2.1 按类目寻找参照

| 类目 | 首要侦察对象 | 官方参照系统 |
|---|---|---|
| 物品/装备 | 原型表、品质、子类型、叠加上限、词条结构 | 打造、掉落、宝箱 |
| 货币/属性/点数 | 独立数值类或统一属性枚举、完整清单 | GM/调试窗口、奖励结算 |
| 技能 | 技能表、等级/品阶、分支和前置 | 学习、升级流程 |
| 任务 | 任务表、状态机、接取前置 | 接任务、交任务流程 |
| 存档/进度 | 序列化结构、版本和加密方式 | 存档、读档、自动存档 |
| 战斗/数值 | 属性枚举、Buff、结算点 | 装备加成、被动、Buff 流程 |
| 商店/交易 | 商品表、价格、库存刷新 | 开店、刷新商品 |
| 地图/传送 | 场景表、坐标、解锁标记 | 传送点、场景切换 |
| 外观/模型 | 资源路径、皮肤/换装表 | 换装、幻化 |

### 2.2 官方产出规则

凡是游戏正常产出的结构化对象，都应先追踪它的生成规则，再手工调用添加 API。例如装备可能需要品质对应的词条组和词条数量；任务可能需要合法初始状态；技能可能需要成长或套路关联。只传 ID、数量或品质，可能得到默认空字段、错误子类型或 UI 过滤结果。

具体“品质→词条组”“子类型→套路”“任务状态值”等映射属于项目事实，写入 `MOD-MEMORY.md`，不要硬编码进本文档。

### 2.3 跨类目必查

- 目标数据是明文程序集、AssetBundle、热更新资源还是加密数据？读不出时转从代码逻辑、官方调试入口和 UI 调用链入手。
- 玩家、背包、数据表、场景和管理器是否已初始化？未就绪时应等待或重试，不能直接解引用。
- 游戏是否会清理外部创建的 `MonoBehaviour`？必须用最小日志实测。
- 写入是否触发存档、联网校验、反作弊或其他外部副作用？按目标游戏实际情况验证。

---

## 3. 读—改—写实现规范

### 3.1 总纲

1. **读**：读取原生参数和当前值，保存基准值。
2. **改**：只改目标字段，使用官方写入 API；明确绝对设置与增量修改。
3. **写**：应用后重新读取，验证结果、缓存、事件和 UI；异常记录上下文并隔离影响。

一句话：**写之前先读，改最小字段，写完验证。**

### 3.2 数值型：货币、属性、点数、等级

- 先列出完整数值清单和单位、上下限、初始化条件。
- 明确写入 API 是增量还是绝对设置；没有确认参数语义前，不要做批量修改。
- 货币页、属性页和点数页分离，避免一个错误影响全部数值。

**数值 UI 的完整闭环：**

1. **读取按钮**：从游戏读取每项当前值，填入对应输入框，并把这次读取结果保存为 `baseline`（基准值）。
2. **用户编辑**：输入框代表用户希望的最终值，不代表要直接传给 API 的增量。
3. **确认按钮**：先解析和校验输入值（数字格式、最小值、上限和字段类型）；若 API 是增量写入，计算 `diff = desiredValue - baseline`，再把 `diff` 传入；若 API 是绝对设置，直接传 `desiredValue`。
4. **写入后重新读取**：不要直接相信输入框或 API 返回值；重新从游戏读取真实值，更新输入框和新的 `baseline`。
5. **反馈结果**：显示成功/失败统计和异常日志；部分字段失败时，不要把全部字段标记为成功。
6. **分离页面状态**：货币页、属性页和点数页分别维护自己的读取按钮、确认按钮、基准值和错误反馈，互不复用隐式状态。

伪代码：

```csharp
void ReadValues()
{
    foreach (var entry in entries)
    {
        var current = ReadFromGame(entry.Type);
        entry.Baseline = current;
        entry.InputText = current.ToString(CultureInfo.InvariantCulture);
    }
}

void ApplyValues()
{
    foreach (var entry in entries)
    {
        if (!TryParseDesired(entry.InputText, out var desired))
            continue;

        var change = entry.UsesDeltaApi
            ? desired - entry.Baseline
            : desired;
        WriteToGame(entry.Type, change);
    }

    // 写入后再次读取，防止 UI 与游戏真实值脱节。
    ReadValues();
}
```

伪代码中的 `ReadFromGame`、`WriteToGame` 和字段类型必须替换为目标游戏的已验证 API；不要把示例签名当作通用接口。

### 3.3 对象型：物品、装备、技能、任务、商品

1. 查找完整原型或官方生成模板。
2. 确认品质、子类型、前置、叠加性和生成字段的语义。
3. 只构造必要字段，调用官方添加/生成 API。
4. 对官方随机或状态生成规则进行补全。
5. 验证对象是否存在、是否出现在对应 UI、是否能正常使用或继续流转。

### 3.4 常用 API 模式

- **静态入口**：从 `Xxx.I`、`Instance` 或官方管理器取得玩家/系统对象。
- **组件字段**：读取玩家已有的背包、属性和状态组件；不要自行 `new` 替代游戏对象。
- **数据表**：遍历官方 `Dictionary<id, prototype>` 或等价表。
- **本地化**：使用游戏官方名称 API，不要把本地化文本硬编码为逻辑 ID。
- **刷新**：优先调用官方刷新事件/方法；反射只作为已确认签名后的兜底。
- **IL2CPP 数组**：使用当前 Il2CppInterop 版本要求的数组类型，例如 `Il2CppStructArray<T>` 或 `Il2CppReferenceArray<T>`；以实际 interop 引用为准。

---

## 4. 工程、部署与逆向

### 4.1 BepInEx 与项目模板

- Mono 和 IL2CPP 使用不同的插件基类、引用和互操作层；不要把 Mono 项目 DLL 或 csproj 直接复制到 IL2CPP 项目。
- 优先使用与当前 BepInEx 分支匹配的官方模板或现有可运行插件作为 csproj 基准。
- Mono 通常从游戏 `*_Data/Managed` 引用逻辑程序集和 Unity 模块；IL2CPP 通常从 `BepInEx/interop` 引用生成的互操作程序集，并按模板补充运行时引用。
- 具体 TargetFramework 以当前模板、BepInEx 分支、插件基类和可运行引用共同决定。

### 4.2 部署与构建

```powershell
dotnet build MyMod.csproj -c Release
Copy-Item bin\Release\MyMod.dll "<GameRoot>\BepInEx\plugins\" -Force
```

部署前确认游戏已关闭、目标目录正确；部署后检查 DLL 时间戳和 BepInEx 日志。建议为每个游戏保留上一稳定版本并提供回滚步骤。

### 4.3 修改器启动自动体检（与 UE 三件套同构）

打开修改器/启动器即自动做，不等人点（逻辑进共享 `deploy.py`，见 UE 侧 `engine/deploy.py` 同构实现）：

- 三件套校验：劫持链（按分支：doorstop 的 `winhttp.dll`/`version.dll` 或对应配置）+ `BepInEx/` 本体目录 + `BepInEx/plugins/<mod>.dll`；缺即用自带包补齐（打进 exe），只补缺失项，不动用户其他插件。
- 本局生效：游戏启动瞬间文件必须就位；启动时缺文件则本局无通道，补完必须重启一次游戏，不要在本局继续测。
- 部署纪律：游戏关闭时复制自家 DLL；部署后核时间戳 + 日志无 Error；补齐 chainloader 类文件后重验分支匹配（Mono/IL2CPP 不混用）。

### 4.4 成品安装器（新用户单文件版，Unity 成品默认按此做）

标准形态：PyInstaller 单文件 `<Game>Setup.exe`（tkinter 界面，`--onefile --windowed`），`payload/` 内嵌 `bepinex.zip` + 自家 MOD DLL，打包脚本三步固定：①`dotnet build` 出最新 DLL ②从金色来源收 payload 打 zip ③PyInstaller 出单文件。实例见各游戏工程的 `Launcher/`（Mono）/`Setup/`（IL2CPP）目录。

安装器必备件（缺一不可）：

- Steam 自动定位：注册表 Steam 路径 → `libraryfolders.vdf` 各库 → `appmanifest_<id>.acf` 的 `installdir` → exe 存在校验；找不到转手动选择 + ini 记忆。
- 三行状态：目录有效性 / BepInEx+MOD 版本状态（自家 DLL 按大小比对判旧）/ 游戏进程（运行中禁用部署和清除）。
- 一键部署：只补缺失项，不动存档、别人的插件和已有的配置；每次新增记入清单 `BepInEx/<Mod>.files.txt`；部署完提示重启一次游戏（本局不生效）。
- 清除按钮：二次确认后按清单删除本次新增 + 自家残留配置，空目录自下而上回收，恢复到部署前；部署前就存在的文件一个不碰。逻辑必须先在假游戏目录实测（部署数 == 清除数，别人文件原样）。
- Steam 调起按钮（`steam://rungameid/<id>`）和说明文案（见下）。

payload 分流（只补缺项的前提下，按构型多收）：

| 构型 | 必收 | 多收 |
|---|---|---|
| Mono（BepInEx 5） | 劫持链（`winhttp.dll`/`version.dll` + doorstop 配置）+ `BepInEx/core` + `BepInEx/patchers` | 无 |
| IL2CPP（BepInEx 6） | 同左 | `BepInEx/interop` + `BepInEx/unity-libs` + `BepInEx/config/BepInEx.cfg`（控制台关，键位以目标分支实物为准）+ `dotnet/`（BepInEx6 运行时，原版游戏没有） |

成品静默（两处，缺一即扰民）：`BepInEx.cfg` 的 `[Logging.Console] Enabled = false`（打包脚本对配置文本强制改写，不依赖人工；分支键位差异以实物为准）；插件自带 `调试/详细日志` 配置默认关闭，轮询/事件/转储类诊断走开关，错误和关键状态常开。调试时分别改回 true。

说明文案规范：**部署成功后不需要再打开安装器，游戏运行自动加载，打开修改器按快捷键**。注意用词：快捷键随时开窗，读档只是功能的前置条件（窗内未就绪提示），不要写成"读档按 F8"。

### 4.5 反编译与运行时分析

| 工具 | 用途 |
|---|---|
| ILSpy / `ilspycmd` | Mono 程序集反编译、全文搜索、批量导出 |
| dnSpyEx | Mono 程序集交叉跳转和调试辅助 |
| Cpp2IL | IL2CPP 元数据/程序集恢复与分析入口 |
| UnityExplorer | 运行时观察场景、GameObject、组件和字段 |
| RuntimeUnityEditor | 运行时查看和修改 Unity 对象的辅助工具 |
| `dumpinfo` 等工具 | 检查 interop 类型、字段和方法签名 |

静态反编译结果是候选，不是运行时事实。IL2CPP 的字段偏移、裁剪和生成类型尤其需要结合版本和运行时日志确认；遇到裁剪导致的方法不可用时，再研究合适的兼容调用或 P/Invoke 兜底，不要默认绕过所有 API。

### 4.6 运行时探针

最小探针只记录必要事实：

- 插件 `Awake`、`Start`、`Update`、`OnDestroy`；
- `Application.unityVersion`、`Application.version`、平台；
- 关键程序集是否能加载；
- 驱动入口是否在场景切换后继续执行；
- 玩家、背包、数据表何时就绪。

日志应节流，不要每帧刷屏。探针确认环境后再加入业务代码。

---

## 5. 运行时、输入与 UI

### 5.1 生命周期与常驻入口

外部创建的 `MonoBehaviour` 可能被游戏清理，但不是所有游戏都会这样。先用 `Awake`、`Update`、`OnGUI` 和 `OnDestroy` 日志确认。

**完整排查链：**

1. 最小探针在 `Awake` 输出一次 `enabled`、`activeSelf` 和对象名；之后对 `Update`、`OnGUI` 做节流 tick 日志，并在 `OnDestroy` 输出销毁证据。
2. 如果 `Awake` 有而 `Update`/`OnGUI` 没有，先确认组件是否被禁用、宿主对象是否被销毁，以及是否有场景切换导致驱动停止。
3. 在反编译文本中搜索 `DontDestroyOnLoad`、`MonoSingleton`、`Singleton`、根级管理器和游戏主循环类，建立候选常驻组件列表。
4. 排除只在登录、标题或某个子场景存在的候选；确认候选在主场景、目标场景和场景切换后仍会执行。
5. 对候选组件的 `Update`、`LateUpdate` 或 UI 入口加临时日志，确认调用频率、对象生命周期和方法签名。
6. 只有确认候选稳定存活后，才选择 Harmony Patch；记录目标类型、方法签名、调用频率和验证日志。

可靠性通常按以下顺序评估：

1. Harmony patch 游戏自身稳定存在的组件；
2. 游戏已确认的常驻对象或静态入口；
3. `AddComponent` 到游戏对象（仅在实测不会被清理时采用）。

示例（签名必须按目标游戏实际类型替换）：

```csharp
var harmony = new Harmony("mod.id");
harmony.Patch(updateMethod,
    postfix: new HarmonyMethod(typeof(Plugin), nameof(Update_Postfix)));
harmony.Patch(onGuiMethod,
    postfix: new HarmonyMethod(typeof(Plugin), nameof(OnGUI_Postfix)));
```

Patch 前确认目标方法唯一性、参数签名、调用频率和对象生命周期。不要只凭方法名相似就注入。

### 5.2 输入与事件来源

- 快捷键只能由一个来源负责切换状态；不要同时在 `Update` 和 `OnGUI` 对同一个按键 toggle。
- 优先使用已经验证可用的输入后端；业务逻辑不直接绑定某个输入库。
- IMGUI 鼠标事件是否可用，必须以事件计数采样为准：在 `OnGUI` 内按 `Event.type` 计数 `MouseDown/MouseUp/MouseMove`，几十次主动点击零命中即判定不通。不要凭"悬停变色/按下闪一下"猜——渲染走通不代表事件走通（曾实测只有 `Layout/Repaint`，点击全部穿透到游戏）。
- 事件不通时，交互优先改走 `Update` 轮询：绘制只负责显示 + 登记控件矩形；点击用 `Input.GetMouseButtonDown/Up` + `Input.mousePosition` 做"按下/抬起在同一控件才触发"，坐标换算为 `guiPos = (mouse.x, Screen.height - mouse.y)`，再按目标分辨率/DPI 实测校准；拖拽同理，打字用 `Input.inputString` 轮询（含退格/回车/粘贴，中文 IME 需实测，过滤类输入准备 ID 数字通道）。P/Invoke 读屏幕坐标做命中曾因 DPI 错位 + 与 `GUI.Button`/`GUI.DragWindow` 双轨互顶实锤失败，选用前必须先实测验证，不做默认兜底。
- 不要预设 `MonoBehaviour.OnGUI` 之外的静态 GUI 入口存在；先检查目标 Unity 程序集和运行时行为。

### 5.3 IMGUI 窗口约定

1. **深色不透明背景，使用双保险**：
   - 准备一张 1x1、alpha 为 1 的深色 `Texture2D`，设置 `HideFlags.HideAndDontSave`。
   - 基于 `GUI.skin.window` 创建窗口样式，把 `normal`、`active`、`hover`、`focused` 以及对应的 `on*` 状态的 `.background` 全部指向这张纹理，并将文字色设为白色。
   - 调用 `GUI.Window(id, rect, DrawWindow, title, windowStyle)` 时显式传入自定义样式；漏掉 style 参数会退回默认半透明窗口。
   - 如果目标环境中仅设置 `GUIStyle` 不稳定，在窗口回调开头再铺一层不透明底，绘制内容前恢复颜色：

```csharp
private static readonly Color WindowColor = new Color(0.10f, 0.11f, 0.12f, 1f);

// 伪代码：windowWidth/windowHeight/titleHeight 为自家窗口宽/高/标题高，按目标分辨率实测填写。
private void DrawWindow(int id)
{
    var oldColor = GUI.color;
    GUI.color = WindowColor;
    GUI.DrawTexture(new Rect(0f, 0f, windowWidth, windowHeight),
        Texture2D.whiteTexture);
    GUI.color = oldColor;

    // 在这里绘制 Tab、按钮和内容。
    GUI.DragWindow(new Rect(0f, 0f, windowWidth, titleHeight));
}
```

   这条回调内绘制是兜底，不应替代对样式状态的正确设置；两层同时使用可降低不同 Unity/BepInEx 环境下的透明背景问题。
2. **Tab 不覆盖标题拖拽区**：标题栏约占顶部 30px，Tab 从标题栏下方开始；先处理 Tab/内容按钮命中，再把未命中的标题区交给拖拽。可使用 `yTab = TITLE_H + margin`、`CONTENT_TOP = yTab + TAB_H`，列表和翻页区域避开标题栏及底部翻页条。
3. 中文字体应使用目标系统可用字体，并统一设置 Label 样式；字体设置和颜色问题以实际游戏渲染结果为准。
4. **字体放大只改窗口内**：在窗口回调入口暂存 `GUI.skin` 的 label/button/textField/toggle 字号，设大后绘制，`try/finally` 恢复，不污染游戏自带 UI；OS 字体按可用列表创建一次并缓存。字号按目标分辨率实测确定。
5. **放大后防溢出**：过滤栏拆行（类型独占一行，选项类放第二行），列表行高/步进与字号同步加大，输入框同步加宽；验收标准是最大字号下无控件挤出窗口。
6. **档位走输入框，不走按钮**：品质/等阶这类枚举档位用手动输入框 + 合法范围钳制，越界/非法按默认值处理并提示；会产生坏数据的越界档位不给快捷按钮。批量快捷按钮（如 +999/添加 100 类）默认不给，数量走手动输入框；确需快捷先实测坏数据边界。

---

## 6. 代码规范与故障隔离

- **模块化**：UI 只负责绘制和回调，输入层只负责检测，业务层只调游戏 API，数据层只读/缓存；新增功能优先新增方法和分支，不改动无关功能。
- **故障隔离**：在插件入口、Harmony 回调、输入回调和 UI 回调设置边界异常处理；业务逻辑使用精确 `catch`，记录完整上下文，避免空 `catch` 吞错。
- **无全局污染**：不修改游戏原有数据结构；缓存使用副本，写入走官方 API。
- **前置检查**：调用前检查管理器、玩家、背包、数据表和场景是否就绪；未就绪时等待、重试或给出可诊断日志。
- **日志**：统一 `[TAG]` 前缀（`[DIAG]`/`[EV]` 等按需扩展）；`Awake` 输出加载、版本和绑定键，作为插件生效的第一证据。

---

## 7. 验证、排障与回滚

### 7.1 最小验证清单

- [ ] 插件被扫描，且日志无加载异常
- [ ] 快捷键可触发且不与游戏冲突
- [ ] 玩家/数据表未就绪时不崩溃
- [ ] 读取值与游戏界面一致
- [ ] 写入后再次读取值正确
- [ ] 对象出现在正确 UI，且字段完整
- [ ] 重复操作不会重复叠加
- [ ] 场景切换后仍按预期工作
- [ ] 异常有日志且不会拖垮其他功能
- [ ] 已备份并验证回滚路径

### 7.2 常见症状速查

| 症状 | 可能原因 | 下一步动作 |
|---|---|---|
| 启动即退出 | Steam/启动器要求、版本或启动参数不符 | 查游戏和启动器日志；确认 Steam/AppID、游戏版本、BepInEx 分支和启动参数；不要只看退出码 |
| 插件未加载 | DLL 位置、GUID、运行时分支或引用版本错误 | 确认 DLL 位于目标 `plugins` 目录；查 `LogOutput.log`；核对插件 GUID、基类、BepInEx 和 interop 引用 |
| `Awake` 有但 `Update`/`OnGUI` 无 | 外部对象被清理、组件被禁用、驱动入口错误 | 打生命周期 tick 和 `OnDestroy` 日志；搜索 `DontDestroyOnLoad`/`MonoSingleton`；确认常驻组件后再 Harmony Patch |
| 按键无反应 | 输入后端不匹配、游戏占用、多个来源抵消 | 查实际输入 DLL/调用链；单独验证输入后端；换无冲突键；显隐 toggle 只保留一个来源 |
| 数据改了但 UI 不变 | UI 刷新事件缺失、缓存未重算、对象被 UI 过滤 | 重新读取确认数据；查官方刷新事件/重算方法；检查过滤条件和场景时机 |
| 物品存在但不可见/不可用 | 子类型、前置、叠加性、生成字段或 UI 过滤错误 | 对照官方掉落/打造调用链；补齐合法子类型和生成字段；调用已验证的刷新机制 |
| 装备无附加属性 | 只传 ID/品质，未复现官方生成规则 | 追踪官方打造或掉落调用链，确认生成规则（如词缀组/数量映射）后再写入并重新读取 |
| 数值重复叠加 | 把绝对值传给增量 API，或没有保存基准值 | 读取时保存 `baseline`；确认时使用 `desired - baseline`；写后再次读取并更新基准值 |
| `DllNotFoundException` | HintPath、运行时 DLL 或平台位数不匹配 | 检查 csproj 引用、目标目录和 x86/x64；用当前游戏实际 DLL，不要复制旧项目路径 |
| `TypeLoadException` | BepInEx、interop、插件引用版本混用 | 核对当前游戏 BepInEx 分支、interop 生成版本和插件基类；清理旧引用后重建 |
| `NotSupportedException` | IL2CPP 裁剪或互操作层限制 | 先确认方法签名、版本和调用时机；再选择官方替代入口、兼容调用或 P/Invoke 兜底 |

### 7.3 回滚

- 游戏运行中不要覆盖被锁定的插件 DLL。
- 保留上一稳定 DLL 和配置；出现崩溃、数据写入异常或不可逆副作用时先恢复。
- 回滚后重新启动并检查 BepInEx 日志、目标 UI 和存档状态。

---

## 8. 项目记忆规范

通用文档只保留方法；项目 `MOD-MEMORY.md` 至少记录：

1. **环境**：游戏路径、游戏/Unity/BepInEx 版本、Mono/IL2CPP 证据、TargetFramework、csproj、反编译和 interop 目录。
2. **启动与输入**：Steam AppID/启动命令、原有快捷键、MOD 键位、实际可用输入 API。
3. **生命周期**：稳定宿主类和方法、是否清理外部对象、Patch 签名、场景和就绪条件。
4. **目标系统六问答案**：具体类、字段、枚举、读取/写入签名、参数语义、刷新机制、官方产出调用链。
5. **已验证陷阱**：词条映射、子类型过滤、UI 刷新、场景限制、已知崩溃和解决方式。
6. **进度**：功能清单、当前状态、已知问题、下一步。
7. **部署与回滚**：DLL 路径、构建/复制命令、稳定版本备份、回滚步骤和验证结果。

判断规则见 §0。

---

## 9. 官方与生态参考

- [BepInEx 文档](https://docs.bepinex.dev/)：安装、插件开发、API 和开发工具。
- [BepInEx 主仓库](https://github.com/BepInEx/BepInEx)：发行版、兼容性、Issue 和版本变化。
- [BepInEx.PluginTemplates](https://github.com/BepInEx/BepInEx.PluginTemplates)：按当前分支生成项目骨架，优先于复制旧 csproj。
- [Harmony](https://github.com/pardeike/Harmony) / [HarmonyX](https://github.com/BepInEx/HarmonyX)：运行时 Patch；以目标环境实际提供的版本为准。
- [Il2CppInterop](https://github.com/BepInEx/Il2CppInterop)：IL2CPP 互操作程序集和运行时类型。
- [Cpp2IL](https://github.com/SamboyCoding/Cpp2IL)：IL2CPP 元数据和程序集分析入口。
- [ILSpy](https://github.com/icsharpcode/ILSpy) / [dnSpyEx](https://github.com/dnSpyEx/dnSpy)：Mono 程序集分析。
- [UnityExplorer](https://github.com/sinai-dev/UnityExplorer) / [RuntimeUnityEditor](https://github.com/ManlyMarco/RuntimeUnityEditor)：运行时观察辅助工具。

这些工具负责收集证据或提出候选，不能替代目标游戏中的运行时验证。
