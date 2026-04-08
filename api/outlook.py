from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
from services.mail_imports import MailImportExecuteRequest, mail_import_registry

router = APIRouter(prefix="/outlook", tags=["微软邮箱（Outlook / Hotmail）"])


# MODIFIED BY Soein fork for bug #3-b:
# 新增"复活已消耗 Hotmail 号"的路由。
# 配合 core/base_mailbox.py 的软删除改动（_pop_account 用 enabled=False 代替 session.delete），
# 用户可以通过 API 把"注册失败但被标记为 used"的号重新加入池子。
class RestoreResult(BaseModel):
    ok: bool
    email: Optional[str] = None
    enabled: Optional[bool] = None
    restored: Optional[int] = None


@router.post("/accounts/{email}/restore", response_model=RestoreResult)
def restore_outlook_account(email: str):
    """复活单个 enabled=False 的微软邮箱号，让它重新可用于注册任务。"""
    from core.db import engine, OutlookAccountModel
    from sqlmodel import Session, select

    with Session(engine) as s:
        acc = s.exec(
            select(OutlookAccountModel).where(OutlookAccountModel.email == email)
        ).first()
        if not acc:
            raise HTTPException(status_code=404, detail=f"账号不存在: {email}")
        acc.enabled = True
        # 保留 last_used 作为审计证据，不重置
        s.add(acc)
        s.commit()
        return RestoreResult(ok=True, email=email, enabled=True)


@router.post("/accounts/restore-all-disabled", response_model=RestoreResult)
def restore_all_disabled_outlook_accounts():
    """批量复活所有 enabled=False 的微软邮箱号。"""
    from core.db import engine, OutlookAccountModel
    from sqlmodel import Session, select

    with Session(engine) as s:
        rows = s.exec(
            select(OutlookAccountModel).where(OutlookAccountModel.enabled == False)
        ).all()
        count = 0
        for r in rows:
            r.enabled = True
            s.add(r)
            count += 1
        s.commit()
        return RestoreResult(ok=True, restored=count)


class OutlookBatchImportRequest(BaseModel):
    data: str
    enabled: bool = True


class OutlookBatchImportResponse(BaseModel):
    total: int
    success: int
    failed: int
    accounts: List[Dict[str, Any]]
    errors: List[str]


@router.post("/batch-import", response_model=OutlookBatchImportResponse)
def batch_import_outlook(request: OutlookBatchImportRequest):
    """
    批量导入微软邮箱（Outlook / Hotmail）账户

    支持两种格式（每行一个账户，字段用 ---- 分隔）：
    - 邮箱----密码
    - 邮箱----密码----client_id----refresh_token

    运行时默认优先使用 Graph 后端读取邮件；若账号缺少 OAuth 凭据则自动回退到 IMAP。
    """
    try:
        strategy = mail_import_registry.get("microsoft")
        result = strategy.execute(
            MailImportExecuteRequest(
                type="microsoft",
                content=request.data,
                enabled=request.enabled,
            )
        )
        return OutlookBatchImportResponse(
            total=result.summary.total,
            success=result.summary.success,
            failed=result.summary.failed,
            accounts=list(result.meta.get("accounts") or []),
            errors=result.errors,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

