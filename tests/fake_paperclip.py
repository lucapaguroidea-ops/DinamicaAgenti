"""A fake Paperclip for tests: the API calls the kit makes, in memory (R2 shapes)."""

import re

from kit.paperclip import PaperclipError


class Fake:
    def __init__(self, fail_at: int | None = None):
        self.calls: list[tuple[str, str, dict | None]] = []
        self.issues: dict[str, dict] = {}
        self.cards: dict[str, list[dict]] = {}
        self.comments: dict[str, list[str]] = {}
        self.n, self.fail_at = 0, fail_at

    def _id(self, prefix: str) -> str:
        self.n += 1
        return f"{prefix}-{self.n}"

    def request(self, method, path, body=None):
        if self.fail_at is not None and len(self.calls) == self.fail_at:
            raise PaperclipError(500, method, path, "down")
        self.calls.append((method, path, body))
        if m := re.fullmatch(r"/api/companies/[^/]+/issues", path):
            iid = self._id("iss")
            self.issues[iid] = dict(body, id=iid)
            return self.issues[iid]
        if m := re.fullmatch(r"/api/issues/([^/]+)", path):
            if method == "GET":
                return self.issues[m.group(1)]
            self.issues[m.group(1)].update({k: v for k, v in body.items() if k != "comment"})
            if body.get("comment"):
                self.comments.setdefault(m.group(1), []).append(body["comment"])
            return self.issues[m.group(1)]
        if m := re.fullmatch(r"/api/issues/([^/]+)/comments", path):
            self.comments.setdefault(m.group(1), []).append(body["body"])
            return {"id": self._id("cmt")}
        if m := re.fullmatch(r"/api/issues/([^/]+)/interactions", path):
            rows = self.cards.setdefault(m.group(1), [])
            if method == "GET":
                return rows
            same = [r for r in rows if r["idempotencyKey"] == body["idempotencyKey"]]
            if same:
                return same[0]
            row = dict(body, id=self._id("int"), status="pending", result=None)
            rows.append(row)
            return row
        return {"id": self._id("obj")}

    def resolve(self, pid, status, result, user="user-acc", agent=None):
        row = [r for r in self.cards[pid] if r["status"] == "pending"][-1]
        row.update(status=status, result=result, resolvedByUserId=user, resolvedByAgentId=agent)
        return row
