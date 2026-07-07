#include "term_buf.h"

#include <furi.h>
#include <string.h>

typedef struct {
    char (*lines)[TERM_LINE_LEN];
    int head;  /* index of the oldest line */
    int count; /* number of valid lines */
    FuriMutex* mutex;
} TermBuf;

static TermBuf tb = {0};

void term_buf_init(void) {
    if(tb.lines) return;
    tb.lines = malloc(TERM_MAX_LINES * TERM_LINE_LEN);
    furi_check(tb.lines != NULL);
    tb.head = 0;
    tb.count = 0;
    tb.mutex = furi_mutex_alloc(FuriMutexTypeNormal);
}

void term_buf_free(void) {
    if(!tb.lines) return;
    furi_mutex_free(tb.mutex);
    free(tb.lines);
    memset(&tb, 0, sizeof(tb));
}

void term_buf_clear(void) {
    if(!tb.lines) return;
    furi_mutex_acquire(tb.mutex, FuriWaitForever);
    tb.head = 0;
    tb.count = 0;
    furi_mutex_release(tb.mutex);
}

void term_buf_append(const char* line) {
    if(!tb.lines || !line) return;
    furi_mutex_acquire(tb.mutex, FuriWaitForever);
    int slot;
    if(tb.count < TERM_MAX_LINES) {
        slot = (tb.head + tb.count) % TERM_MAX_LINES;
        tb.count++;
    } else {
        slot = tb.head;
        tb.head = (tb.head + 1) % TERM_MAX_LINES;
    }
    strncpy(tb.lines[slot], line, TERM_LINE_LEN - 1);
    tb.lines[slot][TERM_LINE_LEN - 1] = '\0';
    furi_mutex_release(tb.mutex);
}

int term_buf_count(void) {
    if(!tb.lines) return 0;
    furi_mutex_acquire(tb.mutex, FuriWaitForever);
    int n = tb.count;
    furi_mutex_release(tb.mutex);
    return n;
}

bool term_buf_get(int index, char* out, int out_size) {
    if(!tb.lines || !out || out_size <= 0) return false;
    bool ok = false;
    furi_mutex_acquire(tb.mutex, FuriWaitForever);
    if(index >= 0 && index < tb.count) {
        int slot = (tb.head + index) % TERM_MAX_LINES;
        strncpy(out, tb.lines[slot], out_size - 1);
        out[out_size - 1] = '\0';
        ok = true;
    }
    furi_mutex_release(tb.mutex);
    return ok;
}
