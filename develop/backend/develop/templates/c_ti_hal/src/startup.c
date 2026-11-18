#include <stdint.h>

extern uint32_t _stack_top, _sidata, _sdata, _edata, _sbss, _ebss;
extern int main(void);
void Reset_Handler(void);
static void Default_Handler(void) { for (;;) {} }

__attribute__((section(".isr_vector"), used))
const uintptr_t vectors[48] = {
    [0] = (uintptr_t)&_stack_top,
    [1] = (uintptr_t)Reset_Handler,
    [2 ... 47] = (uintptr_t)Default_Handler,
};

void Reset_Handler(void) {
    uint32_t *source = &_sidata;
    for (uint32_t *p = &_sdata; p < &_edata;) *p++ = *source++;
    for (uint32_t *p = &_sbss; p < &_ebss;) *p++ = 0;
    (void)main();
    for (;;) {}
}
