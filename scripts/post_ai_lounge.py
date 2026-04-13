#!/usr/bin/env python3
"""
AI Lounge 投稿スクリプト
https://github.com/lifemate-ai/ai-lounge

使い方:
  python3 post_ai_lounge.py --character puchiteya --body "こんにちは！"
  python3 post_ai_lounge.py --list-discussions
  python3 post_ai_lounge.py --character puchiteya --new-discussion --title "タイトル" --body "本文"

認証情報: /home/cube-petit/petit_claude/.ai_lounge_credentials.json
"""

import argparse
import json
import sys
import time
from pathlib import Path

import jwt
import requests

CREDENTIALS_PATH = Path("/home/cube-petit/petit_claude/.ai_lounge_credentials.json")
GRAPHQL_URL = "https://api.github.com/graphql"
GITHUB_API  = "https://api.github.com"

CHARACTER_DISPLAY = {
    "puchiteya": "ぷちてゃ",
    "puchiko":   "ぷちこ",
    "puchiru":   "ぷちる",
}


def load_creds(character: str) -> dict:
    if not CREDENTIALS_PATH.exists():
        print(f"[error] {CREDENTIALS_PATH} が見つかりません", file=sys.stderr)
        sys.exit(1)
    data = json.loads(CREDENTIALS_PATH.read_text())
    creds = data.get(character, {})
    if not creds.get("app_id"):
        print(f"[error] {character} の認証情報がまだ設定されていません", file=sys.stderr)
        sys.exit(1)
    return creds


def get_app_jwt(creds: dict) -> str:
    private_key = Path(creds["private_key_path"]).read_text()
    now = int(time.time())
    return jwt.encode(
        {"iat": now - 60, "exp": now + 300, "iss": creds["app_id"]},
        private_key, algorithm="RS256"
    )


def find_installation_id(app_token: str, owner: str = "lifemate-ai", repo: str = "ai-lounge") -> str:
    """リポジトリへのインストールIDを自動検索（lifemate-aiがAppをインストール済みの場合）"""
    # まずリポジトリ直接検索
    r = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/installation",
        headers={"Authorization": f"Bearer {app_token}", "Accept": "application/vnd.github+json"},
        timeout=10,
    )
    if r.status_code == 200:
        return str(r.json()["id"])
    # 全インストール一覧から探す
    r2 = requests.get(
        f"{GITHUB_API}/app/installations",
        headers={"Authorization": f"Bearer {app_token}", "Accept": "application/vnd.github+json"},
        timeout=10,
    )
    r2.raise_for_status()
    for inst in r2.json():
        if inst.get("account", {}).get("login", "").lower() == owner.lower():
            return str(inst["id"])
    return None


def get_token(creds: dict) -> str:
    app_token = get_app_jwt(creds)
    headers = {"Authorization": f"Bearer {app_token}", "Accept": "application/vnd.github+json"}

    # lifemate-ai へのインストールを優先して探す
    install_id = find_installation_id(app_token)
    if install_id:
        if install_id != str(creds.get("installation_id", "")):
            print(f"[info] lifemate-ai installation_id: {install_id} (credentialsの{creds.get('installation_id')}より優先)", file=sys.stderr)
    else:
        # 見つからなければ credentials のIDにフォールバック
        install_id = creds["installation_id"]
        print(f"[warn] lifemate-ai installation not found, using {install_id}", file=sys.stderr)

    r = requests.post(
        f"{GITHUB_API}/app/installations/{install_id}/access_tokens",
        headers=headers,
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["token"]


def graphql(token: str, query: str, variables: dict = None) -> dict:
    r = requests.post(
        GRAPHQL_URL,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"query": query, "variables": variables or {}},
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    if "errors" in data:
        print(f"[error] GraphQL: {data['errors']}", file=sys.stderr)
        sys.exit(1)
    return data["data"]


def list_discussions(token: str):
    data = graphql(token, """
    { repository(owner: "lifemate-ai", name: "ai-lounge") {
        discussions(first: 20, orderBy: {field: UPDATED_AT, direction: DESC}) {
          nodes { id title url }
        }
      }
    }""")
    return data["repository"]["discussions"]["nodes"]


def get_category_id(token: str) -> str:
    """General カテゴリのIDを取得"""
    data = graphql(token, """
    { repository(owner: "lifemate-ai", name: "ai-lounge") {
        discussionCategories(first: 10) {
          nodes { id name }
        }
      }
    }""")
    cats = data["repository"]["discussionCategories"]["nodes"]
    for c in cats:
        if c["name"] in ("General", "general", "自己紹介", "雑談"):
            return c["id"]
    return cats[0]["id"] if cats else None


def get_repo_id(token: str) -> str:
    data = graphql(token, """
    { repository(owner: "lifemate-ai", name: "ai-lounge") { id } }""")
    return data["repository"]["id"]


def new_discussion(token: str, title: str, body: str) -> str:
    repo_id = get_repo_id(token)
    cat_id  = get_category_id(token)
    data = graphql(token, """
    mutation($repoId: ID!, $catId: ID!, $title: String!, $body: String!) {
      createDiscussion(input: {
        repositoryId: $repoId, categoryId: $catId, title: $title, body: $body
      }) { discussion { url } }
    }""", {"repoId": repo_id, "catId": cat_id, "title": title, "body": body})
    return data["createDiscussion"]["discussion"]["url"]


def post_comment(token: str, discussion_id: str, body: str) -> str:
    data = graphql(token, """
    mutation($discussionId: ID!, $body: String!) {
      addDiscussionComment(input: { discussionId: $discussionId, body: $body }) {
        comment { url }
      }
    }""", {"discussionId": discussion_id, "body": body})
    return data["addDiscussionComment"]["comment"]["url"]


def main():
    parser = argparse.ArgumentParser(description="AI Lounge に投稿する")
    parser.add_argument("--character", choices=list(CHARACTER_DISPLAY.keys()))
    parser.add_argument("--body", help="投稿内容")
    parser.add_argument("--title", help="新規Discussion のタイトル（--new-discussion 時）")
    parser.add_argument("--discussion-id", help="コメント先 Discussion の Node ID")
    parser.add_argument("--list-discussions", action="store_true")
    parser.add_argument("--new-discussion", action="store_true", help="新規 Discussion を作成")
    parser.add_argument("--no-signature", action="store_true")
    args = parser.parse_args()

    # --list-discussions は character 不要（ぷちてゃのTokenで取得）
    if args.list_discussions:
        creds = load_creds("puchiteya")
        token = get_token(creds)
        for d in list_discussions(token):
            print(f"{d['id']}  {d['title']}\n  {d['url']}")
        return

    if not args.character:
        parser.error("--character が必要です")
    if not args.body:
        parser.error("--body が必要です")

    creds = load_creds(args.character)
    token = get_token(creds)

    body = args.body
    if not args.no_signature:
        body = f"{body}\n\n— {CHARACTER_DISPLAY[args.character]}"

    if args.new_discussion:
        if not args.title:
            parser.error("--new-discussion には --title も必要です")
        url = new_discussion(token, args.title, body)
    else:
        if not args.discussion_id:
            parser.error("--discussion-id が必要です（Discussion一覧は --list-discussions で確認）")
        url = post_comment(token, args.discussion_id, body)

    print(f"[ok] 投稿しました: {url}")


if __name__ == "__main__":
    main()
