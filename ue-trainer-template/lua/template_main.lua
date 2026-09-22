-- 通用 UE4SS Lua 模板 (每个新游戏复制一份,只改 GIVE 与 HOOK 段).
-- 约定: 外部 UI 写 cmd.txt 下发命令,本脚本 LoopAsync 轮询执行,结果写 [LVT] 日志.
-- agent 任务: 按目标游戏六问填 GIVE_FUNC / FREE_HOOKS,其余不动.

local MOD_NAME = "GameTrainer"

local function LVT(s) print("[LVT] " .. s) end

-- ============ 1. 官方发奖 (物品添加,按游戏换) ============
-- 例: local bls = FindFirstOf("BirdLetterSystem")
--     bls:AwardSomeItems(id, n)
local function GiveItem(id, n)
    -- TODO(agent): 换成目标游戏的官方发奖链
    LVT("GiveItem 未配置")
    return false
end

-- ============ 2. 免费 hook (检查端放行,按游戏换) ============
local free_hooks = {}  -- {handle1, handle2...}
local function FreeOn()
    -- TODO(agent): RegisterHook(检查函数全路径, function(self,...) return true end)
    -- 例: CheckResources + TipsCheckResources 双 hook
    LVT("free on (TODO: 填真 hook)")
end
local function FreeOff()
    for _, h in ipairs(free_hooks) do pcall(function() UnregisterHook(h) end) end
    free_hooks = {}
    LVT("free off")
end

-- ============ 3. 命令框架 (不动) ============
local CMDS = {}
local function reg(name, fn) CMDS[name] = fn end

reg("give", function(p)
    local id, n = p:match("^(%d+)%s+(%d+)")
    id, n = tonumber(id), tonumber(n)
    if not id or not n then LVT("用法: lv_give <ID> <数量>") return end
    local ok = GiveItem(id, n)
    pcall(function()
        local pc = UEHelpers.GetPlayerController()
        pc:BroadcastUpdateResource()
    end)
    LVT(string.format("give %d x%d %s", id, n, ok and "OK" or "FAIL"))
end)

reg("free", function(p)
    if p:match("on") then FreeOn() else FreeOff() end
end)

-- cmd.txt 轮询 (写.tmp再整体替换由 UI 侧保证)
local cmd_path = "ue4ss/Mods/" .. MOD_NAME .. "/cmd.txt"
LoopAsync(2000, function()
    local f = io.open(cmd_path, "r")
    if not f then return false end
    local body = f:read("*a") or ""
    f:close()
    if body:gsub("%s", "") == "" then return false end
    io.open(cmd_path, "w"):close()  -- 先清空,防重复执行
    for line in body:gmatch("[^\r\n]+") do
        local cmd, p = line:match("^(%S+)%s*(.*)$")
        cmd = (cmd or ""):gsub("^lv_", "")
        local fn = CMDS[cmd]
        if fn then
            local ok, err = pcall(fn, p or "")
            if not ok then LVT("exec err " .. tostring(err)) end
        else
            LVT("未知命令 " .. tostring(cmd))
        end
        print("exec done")  -- UI 侧计数用
    end
    return false
end)

print("[LVT] loaded " .. MOD_NAME)
