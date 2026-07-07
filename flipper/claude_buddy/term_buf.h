#pragma once

/* Terminal ring buffer (Bridge mode).
 *
 * Holds host-wrapped text lines pushed by the Python bridge ("term"
 * protocol messages): Claude's replies, submitted prompts, and rendered
 * slash-command views (/usage, /context, ...).  Heap-allocated so the
 * ~4 KB of line storage stays off the 4 KB app stack.
 *
 * Written from the GUI thread (process_message) and read from the draw
 * callback; guarded by an internal mutex like nus_transcript. */

#include <stdbool.h>

#define TERM_MAX_LINES 200
#define TERM_LINE_LEN 33 /* 32 visible chars + NUL — host wraps at ~25 */

void term_buf_init(void);
void term_buf_free(void);
void term_buf_clear(void);
void term_buf_append(const char* line);
int term_buf_count(void);
/* index 0 = oldest retained line. Returns false when out of range. */
bool term_buf_get(int index, char* out, int out_size);
