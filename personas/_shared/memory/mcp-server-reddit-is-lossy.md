# mcp-server-reddit's models are lossy: a Post exposes only id/title/aut

_2026-08-14 22:21 · persistent_

mcp-server-reddit's models are lossy: a Post exposes only id/title/author/score/subreddit/url/created_at/comment_count/post_type/content (no upvote_ratio, flair, or removal status), SubredditInfo cannot read rules, and image/media posts come back as post_type 'link' with the permalink instead of the body. It cannot tell you whether a post was removed or what a sub's rules are; that needs another source or a human with a browser. The server also needs 'mcp<2' pinned (uvx --with 'mcp<2' mcp-server-reddit) or it crashes at import.


mcp-server-reddit does not return selftext for image/media posts: get_post_content sets post_type='link' and content=the post's own permalink, so the body is unverifiable. Plain self-posts return post_type='text' with real body text. Never claim a media post's body is intact from this tool.
