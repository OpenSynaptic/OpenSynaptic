#!/usr/bin/env python3
"""
Multi-language demonstration script for OpenSynaptic.

Shows how to: 
1. Switch languages at runtime
2. Use translated messages in logging
3. Configure language in your application
"""

import sys
from pathlib import Path

# Add src to path for local development
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from opensynaptic.utils import (
    os_log,
    LogMsg,
    MESSAGES,
    Language,
    set_language,
    set_language_by_code,
    get_current_language,
    translate,
)


def demo_basic_translation():
    """Demonstrate basic message translation."""
    print("=" * 60)
    print("DEMO: Basic Translation")
    print("=" * 60)
    
    # English (default)
    msg_template = MESSAGES[LogMsg.READY]
    print(f"\nEnglish template: {msg_template}")
    print(f"Current language: {get_current_language()}")
    
    en_text = translate(msg_template, root='/home/user/opensynaptic')
    print(f"Translated: {en_text}")
    
    # Switch to Chinese
    set_language(Language.ZH)
    print(f"\nCurrent language: {get_current_language()}")
    
    zh_text = translate(msg_template, root='/home/user/opensynaptic')
    print(f"Translated: {zh_text}")
    
    # Switch back to English
    set_language(Language.EN)


def demo_logger_translation():
    """Demonstrate logger with automatic translation."""
    print("\n" + "=" * 60)
    print("DEMO: Logger with Translation")
    print("=" * 60)
    
    # English logs
    print("\n--- English Logs ---")
    set_language(Language.EN)
    os_log.log_with_const('info', LogMsg.CLI_READY, mode='interactive')
    os_log.log_with_const('info', LogMsg.CONFIG_SAVED, field='language', value='en')
    os_log.log_with_const('info', LogMsg.PLUGIN_READY, plugin='test_plugin')
    
    # Chinese logs
    print("\n--- Chinese Logs ---")
    set_language(Language.ZH)
    os_log.log_with_const('info', LogMsg.CLI_READY, mode='交互式')
    os_log.log_with_const('info', LogMsg.CONFIG_SAVED, field='language', value='zh')
    os_log.log_with_const('info', LogMsg.PLUGIN_READY, plugin='test_plugin')


def demo_language_switching():
    """Demonstrate language switching via code."""
    print("\n" + "=" * 60)
    print("DEMO: Language Code Switching")
    print("=" * 60)
    
    # Try different language codes
    codes = ['en', 'EN', 'zh', 'ZH', 'invalid_code']
    
    for code in codes:
        set_language_by_code(code)
        lang = get_current_language()
        template = MESSAGES[LogMsg.TIME_SYNCED]
        translated = translate(template, server_time='2026-04-04 10:00:00', host='localhost', port=8080)
        print(f"\nCode '{code}' → Language: {lang}")
        print(f"  Message: {translated}")


def demo_batch_translation():
    """Demonstrate translating multiple messages at once."""
    print("\n" + "=" * 60)
    print("DEMO: Batch Translation")
    print("=" * 60)
    
    test_keys = [
        (LogMsg.DRIVER_MOUNT, {'module': 'UDP', 'source': 'auto-discovery'}),
        (LogMsg.PROTOCOL_REFRESHED, {'layer': 'L4', 'protocol': 'tcp'}),
        (LogMsg.ID_ASSIGNED, {'addr': '192.168.1.100', 'assigned': '42'}),
    ]
    
    for lang_name, lang in [('English', Language.EN), ('Chinese', Language.ZH)]:
        print(f"\n--- {lang_name} ---")
        set_language(lang)
        
        for msg_key, ctx in test_keys:
            template = MESSAGES[msg_key]
            translated = translate(template, **ctx)
            print(f"  {translated}")


if __name__ == '__main__':
    print("\n" + "█" * 60)
    print("OpenSynaptic Multi-Language Support Demo")
    print("█" * 60)
    
    demo_basic_translation()
    demo_logger_translation()
    demo_language_switching()
    demo_batch_translation()
    
    print("\n" + "=" * 60)
    print("Demo Complete!")
    print("=" * 60)
    print("\nTo use multi-language in your code:")
    print("  from opensynaptic.utils import set_language, Language")
    print("  set_language(Language.ZH)  # Switch to Chinese")
    print("  # All subsequent logs will be in Chinese")
