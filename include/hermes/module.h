/**
 * @file module.h
 * @brief Hermes Module Protocol for native modules
 *
 * This header defines the interface that native modules (C, C++, Rust, etc.)
 * must implement to be managed by Hermes. Modules communicate with Hermes
 * via POSIX IPC (shared memory, semaphores, named pipes).
 *
 * Lifecycle:
 *   1. Hermes spawns module process with shm_name and config_path args
 *   2. Module calls hermes_module_init() to attach to shared memory
 *   3. Module enters main loop waiting for commands on control pipe
 *   4. On STAGE: module calls hermes_module_stage()
 *   5. On STEP: module executes frame, signals done
 *   6. On TERMINATE: module cleans up and exits
 *
 * Example (C):
 *   int main(int argc, char** argv) {
 *       hermes_context_t* ctx = hermes_module_init(argv[1], argv[2]);
 *       if (!ctx) return 1;
 *
 *       // Main loop
 *       while (hermes_wait_command(ctx)) {
 *           switch (hermes_get_command(ctx)) {
 *               case HERMES_CMD_STAGE:
 *                   my_stage();
 *                   hermes_ack(ctx);
 *                   break;
 *               case HERMES_CMD_STEP:
 *                   my_step(hermes_get_dt(ctx));
 *                   hermes_signal_done(ctx);
 *                   break;
 *               case HERMES_CMD_TERMINATE:
 *                   goto cleanup;
 *           }
 *       }
 *
 *   cleanup:
 *       hermes_module_destroy(ctx);
 *       return 0;
 *   }
 */

#ifndef HERMES_MODULE_H
#define HERMES_MODULE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* --------------------------------------------------------------------------
 * Types
 * -------------------------------------------------------------------------- */

/** Opaque handle to Hermes context */
typedef struct hermes_context hermes_context_t;

/** Command types received from Hermes */
typedef enum {
    HERMES_CMD_NONE = 0,
    HERMES_CMD_STAGE,      /**< Prepare for execution */
    HERMES_CMD_STEP,       /**< Execute one frame */
    HERMES_CMD_RESET,      /**< Reset to initial conditions */
    HERMES_CMD_PAUSE,      /**< Pause execution */
    HERMES_CMD_RESUME,     /**< Resume execution */
    HERMES_CMD_TERMINATE,  /**< Graceful shutdown */
} hermes_command_t;

/** Signal data types */
typedef enum {
    HERMES_TYPE_F64 = 0,  /**< 64-bit float */
    HERMES_TYPE_F32 = 1,  /**< 32-bit float */
    HERMES_TYPE_I64 = 2,  /**< 64-bit signed integer */
    HERMES_TYPE_I32 = 3,  /**< 32-bit signed integer */
    HERMES_TYPE_BOOL = 4, /**< Boolean (stored as u8) */
} hermes_type_t;

/* --------------------------------------------------------------------------
 * Lifecycle Functions
 * -------------------------------------------------------------------------- */

/**
 * Initialize module and attach to Hermes IPC.
 *
 * @param shm_name    Shared memory segment name (e.g., "/hermes_sim")
 * @param config_path Path to module-specific configuration file
 * @return            Context handle, or NULL on error
 */
hermes_context_t* hermes_module_init(const char* shm_name, const char* config_path);

/**
 * Clean up and detach from Hermes IPC.
 *
 * @param ctx Context handle from hermes_module_init()
 */
void hermes_module_destroy(hermes_context_t* ctx);

/* --------------------------------------------------------------------------
 * Command Processing
 * -------------------------------------------------------------------------- */

/**
 * Wait for next command from Hermes.
 *
 * Blocks until a command is received on the control pipe.
 *
 * @param ctx Context handle
 * @return    true if command received, false on error/disconnect
 */
bool hermes_wait_command(hermes_context_t* ctx);

/**
 * Get the current command type.
 *
 * @param ctx Context handle
 * @return    Command type
 */
hermes_command_t hermes_get_command(hermes_context_t* ctx);

/**
 * Acknowledge command completion.
 *
 * @param ctx Context handle
 */
void hermes_ack(hermes_context_t* ctx);

/**
 * Signal that step execution is complete.
 *
 * Must be called after processing HERMES_CMD_STEP.
 *
 * @param ctx Context handle
 */
void hermes_signal_done(hermes_context_t* ctx);

/* --------------------------------------------------------------------------
 * Simulation State
 * -------------------------------------------------------------------------- */

/**
 * Get current frame number.
 *
 * @param ctx Context handle
 * @return    Current frame number
 */
uint64_t hermes_get_frame(hermes_context_t* ctx);

/**
 * Get current simulation time.
 *
 * @param ctx Context handle
 * @return    Current time in seconds
 */
double hermes_get_time(hermes_context_t* ctx);

/**
 * Get timestep.
 *
 * @param ctx Context handle
 * @return    Timestep in seconds
 */
double hermes_get_dt(hermes_context_t* ctx);

/* --------------------------------------------------------------------------
 * Signal Access
 * -------------------------------------------------------------------------- */

/**
 * Get signal value by name.
 *
 * @param ctx    Context handle
 * @param name   Signal name (local, without module prefix)
 * @return       Signal value, or NaN if not found
 */
double hermes_get_signal(hermes_context_t* ctx, const char* name);

/**
 * Set signal value by name.
 *
 * @param ctx    Context handle
 * @param name   Signal name (local, without module prefix)
 * @param value  Value to set
 * @return       true on success, false if signal not found
 */
bool hermes_set_signal(hermes_context_t* ctx, const char* name, double value);

/**
 * Register a signal in shared memory.
 *
 * Must be called during initialization, before STAGE.
 *
 * @param ctx         Context handle
 * @param name        Signal name
 * @param type        Signal data type
 * @param writable    Whether signal can be modified externally
 * @return            true on success
 */
bool hermes_register_signal(
    hermes_context_t* ctx,
    const char* name,
    hermes_type_t type,
    bool writable
);

/* --------------------------------------------------------------------------
 * Utility Macros
 * -------------------------------------------------------------------------- */

/** Check if context is valid */
#define HERMES_VALID(ctx) ((ctx) != NULL)

/** Main loop helper */
#define HERMES_MAIN_LOOP(ctx) while (hermes_wait_command(ctx))

#ifdef __cplusplus
}
#endif

#endif /* HERMES_MODULE_H */
