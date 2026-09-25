# charter-app guard attribution, measured by two mutation probes on PR #85

_2026-09-20 18:42 · persistent_

charter-app guard attribution, measured by two mutation probes on PR #85: contain::open_no_link's O_NONBLOCK alone makes a FIFO test pass without reopen::refuse_unusable (the open returns, the read then fails EAGAIN), and a symlink-at-the-leaf test passes without O_NOFOLLOW because no_link_on_the_way already stats the last component. So of the four tests around a gated read, ONLY the oversized-file one uniquely attributes refuse_unusable. A single 'revert the whole function' mutation kills all four and proves nothing about which guard holds which.
