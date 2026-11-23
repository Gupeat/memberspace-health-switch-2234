# 健康分权重切换影响预估

- 模式：pre（切换前）
- 权重版本：v3 → v4
- 数据日期：2026-11-22
- 生成时间：2026-11-23T00:21:27Z
- 企业总数：500
- 预计状态变化：120
- 冻结状态企业：60（续约/已流失，不进入变化清单）
- 冻结但分数档位会变：6

## 四方向分布

| 方向 | 含义 | 数量 |
|---|---|---:|
| active_to_silent | 活跃→沉默 | 30 |
| silent_to_active | 沉默→活跃 | 30 |
| enter_churn_warning | 进入流失预警 | 30 |
| exit_churn_warning | 退出流失预警 | 30 |

## 按会所

| club_id | 数量 |
|---|---:|
| club-01 | 24 |
| club-02 | 24 |
| club-03 | 24 |
| club-04 | 24 |
| club-05 | 24 |

## 按会员经理

| manager_id | 数量 |
|---|---:|
| mgr-001 | 6 |
| mgr-002 | 6 |
| mgr-003 | 6 |
| mgr-004 | 6 |
| mgr-005 | 6 |
| mgr-006 | 6 |
| mgr-007 | 6 |
| mgr-008 | 6 |
| mgr-009 | 6 |
| mgr-010 | 6 |
| mgr-011 | 6 |
| mgr-012 | 6 |
| mgr-013 | 6 |
| mgr-014 | 6 |
| mgr-015 | 6 |
| mgr-016 | 6 |
| mgr-017 | 6 |
| mgr-018 | 6 |
| mgr-019 | 6 |
| mgr-020 | 6 |

## 明细与口径

- 明细：estimate.csv；分方向/会所/经理交叉计数：pivot.csv。
- 匹配键：company_pid + old_status + new_status + direction；一致率分母为两侧变化行并集。
- 续约（renewed）与已流失（churned）为冻结状态，不进入变化清单；其数量单独保留。
- 报告只含 company_pid、manager_id、club_id 等假名标识。
