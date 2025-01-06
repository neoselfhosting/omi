#include <zephyr/logging/log.h>
#include <zephyr/kernel.h>
#include "transport.h"
#include "mic.h"
#include "utils.h"
#include "led.h"
#include "config.h"
#include "codec.h"
#include "button.h"
#include "sdcard.h"
#include "storage.h"
#include "speaker.h"
#include "usb.h"
#define BOOT_BLINK_DURATION_MS 600
#define BOOT_PAUSE_DURATION_MS 200
#define VBUS_DETECT (1U << 20)
#define WAKEUP_DETECT (1U << 16)
LOG_MODULE_REGISTER(main, CONFIG_LOG_DEFAULT_LEVEL);

static void codec_handler(uint8_t *data, size_t len)
{
    int err = broadcast_audio_packets(data, len);
    if (err)
    {
        LOG_ERR("Failed to broadcast audio packets: %d", err);
    }
}

static void mic_handler(int16_t *buffer)
{
    int err = codec_receive_pcm(buffer, MIC_BUFFER_SAMPLES);
    if (err)
    {
        LOG_ERR("Failed to process PCM data: %d", err);
    }
}

void bt_ctlr_assert_handle(char *name, int type)
{
    LOG_INF("Bluetooth assert: %s (type %d)", name ? name : "NULL", type);
}


bool is_connected = false;
bool is_charging = false;
extern bool is_off;
extern bool usb_charge;
static void boot_led_sequence(void)
{
    // Red blink
    set_led_red(true);
    k_msleep(BOOT_BLINK_DURATION_MS);
    set_led_red(false);
    k_msleep(BOOT_PAUSE_DURATION_MS);
    // Green blink
    set_led_green(true);
    k_msleep(BOOT_BLINK_DURATION_MS);
    set_led_green(false);
    k_msleep(BOOT_PAUSE_DURATION_MS);
    // Blue blink
    set_led_blue(true);
    k_msleep(BOOT_BLINK_DURATION_MS);
    set_led_blue(false);
    k_msleep(BOOT_PAUSE_DURATION_MS);
    // All LEDs on
    set_led_red(true);
    set_led_green(true);
    set_led_blue(true);
    k_msleep(BOOT_BLINK_DURATION_MS);
    // All LEDs off
    set_led_red(false);
    set_led_green(false);
    set_led_blue(false);
}

void set_led_state()
{
    // Recording and connected state - BLUE

    if(usb_charge)
    {
        is_charging = !is_charging;
        if(is_charging)
        {
            set_led_green(true);
        }
        else
        {
            set_led_green(false);
        }
    }
    else
    {
        set_led_green(false);
    }
    if(is_off)
    {
        set_led_red(false);
        set_led_blue(false);
        return;
    }
    if (is_connected)
    {
        set_led_blue(true);
        set_led_red(false);
        return;
    }

    // Recording but lost connection - RED
    if (!is_connected)
    {
        set_led_red(true);
        set_led_blue(false);
        return;
    }

}

int main(void)
{
    int err;
    uint32_t reset_reas = NRF_POWER->RESETREAS;
    NRF_POWER->DCDCEN=1;
    NRF_POWER->DCDCEN0=1;
    NRF_POWER->RESETREAS=1;

    LOG_INF("Omi device firmware starting...");
    err = led_start();
    if (err)
    {
        LOG_ERR("Failed to initialize LEDs (err %d)", err);
        return err;
    }

    // Run the boot LED sequence
    boot_led_sequence();

    // Enable battery
#ifdef CONFIG_ENABLE_BATTERY
    err = battery_init();
    if (err)
    {
        LOG_ERR("Battery init failed (err %d)", err);
        return err;
    }
    err == battery_charge_start();
    if (err)
    {
        LOG_ERR("Battery failed to start (err %d)", err);
        return err;
    }
    LOG_INF("Battery initialized");
#endif

    // Enable button
#ifdef CONFIG_ENABLE_BUTTON
    err = button_init();
    if (err)
    {
        LOG_ERR("Failed to initialize Button (err %d)", err);
        return err
    }
    LOG_INF("Button initialized");
    activate_button_work();
#endif

    // Enable accelerometer
#ifdef CONFIG_ACCELEROMETER
    err = accel_start();
    if (err)
    {
        LOG_ERR("Accelerometer failed to activated (err %d)", err);
        return err
    }
    LOG_INF("Accelerometer initialized");
#endif

    // Enable speaker
#ifdef CONFIG_ENABLE_SPEAKER
    err = speaker_init();
    if (err)
    {
        LOG_ERR("Speaker failed to start");
        return err;
    }
    LOG_INF("Speaker initialized");
#endif

    // Enable sdcard
#ifdef CONFIG_OFFLINE_STORAGE
    err = mount_sd_card();
    if (err)
    {
        LOG_ERR("Failed to mount SD card: %d", err);
        return err
    }
    LOG_INF("SD Card result of mount:%d", err);
#endif

    // Enable haptic
#ifdef CONFIG_ENABLE_HAPTIC
    err = init_haptic_pin();
    if (err)
    {
        LOG_ERR("Failed to initialize haptic pin (err %d)", err);
        return err;
    }
    LOG_INF("Haptic pin initialized");
#endif

    // Enable usb
#ifdef CONFIG_ENABLE_USB
    err = init_usb();
    if (err)
    {
        LOG_ERR("Failed to initialize power supply (err %d)", err);
        return err;
    }
    LOG_INF("USB initialized");
#endif

    // Indicate transport initialization
    set_led_green(true);
    set_led_green(false);

    // Start transport
    int transportErr;
    transportErr = transport_start();
    if (transportErr)
    {
        LOG_ERR("Failed to start transport (err %d)", err);
        // TODO: Detect the current core is app core or net core
        // // Blink green LED to indicate error
        // for (int i = 0; i < 5; i++)
        // {
        //     set_led_green(!gpio_pin_get_dt(&led_green));
        //     k_msleep(200);
        // }
        // set_led_green(false);
        // // return err;
        return err;
    }
    LOG_INF("Transports started");

    play_boot_sound();

    set_led_blue(true);

    // Audio codec(opus) callback
    set_codec_callback(codec_handler);
    err = codec_start();
    if (err)
    {
        LOG_ERR("Failed to start codec: %d", err);
        // Blink blue LED to indicate error
        for (int i = 0; i < 5; i++)
        {
            set_led_blue(!gpio_pin_get_dt(&led_blue));
            k_msleep(200);
        }
        set_led_blue(false);
        return err;
    }

    play_haptic_milli(500);
    set_led_blue(false);

    // Indicate microphone initialization
    set_led_red(true);
    set_led_green(true);

    LOG_INF("Starting microphone initialization");
    set_mic_callback(mic_handler);
    err = mic_start();
    if (err)
    {
        LOG_ERR("Failed to start microphone: %d", err);
        // Blink red and green LEDs to indicate error
        for (int i = 0; i < 5; i++)
        {
            set_led_red(!gpio_pin_get_dt(&led_red));
            set_led_green(!gpio_pin_get_dt(&led_green));
            k_msleep(200);
        }
        set_led_red(false);
        set_led_green(false);
        return err;
    }
    set_led_red(false);
    set_led_green(false);

    // Indicate successful initialization
    LOG_INF("Omi firmware initialized successfully\n");
    set_led_blue(true);
    k_msleep(1000);
    set_led_blue(false);

    // Main loop
    printf("reset reas:%d\n",reset_reas);
    while (1)
    {
        set_led_state();
        k_msleep(500);
    }

    // Unreachable
    return 0;
}

