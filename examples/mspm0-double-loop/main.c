/* MSPM0L2228: use with a SysConfig UART_0 at 115200 baud. */
#include <stdint.h>
#include "ti_msp_dl_config.h"

#define OUTER 256u
#define INNER 256u

/* Volatile keeps both loops and the increment in the generated code. */
static volatile uint32_t count;
static volatile uint32_t outer;
static volatile uint32_t inner;

static void send(const char *s)
{
    while (*s) DL_UART_transmitDataBlocking(UART_0_INST, (uint8_t)*s++);
}

int main(void)
{
    SYSCFG_DL_init();
    for (;;) {
        count = 0;
        for (outer = 0; outer < OUTER; outer++) {
            for (inner = 0; inner < INNER; inner++) {
                count++;
            }
        }
        if (count == OUTER * INNER && outer == OUTER && inner == INNER)
            send("normal\r\n");
        else
            send("ESCAPED\r\n");
    }
}
