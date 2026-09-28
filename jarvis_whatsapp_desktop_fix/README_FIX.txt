JARVIS WhatsApp Desktop Call Fix
================================

Files in this patch:
  main.py
  actions/whatsapp_desktop_call.py

Install:
1. Stop JARVIS (Ctrl+C).
2. Back up your current main.py.
3. Copy this main.py to:
      D:\jarvis-main\jarvis-main\main.py
4. Copy actions\whatsapp_desktop_call.py to:
      D:\jarvis-main\jarvis-main\actions\whatsapp_desktop_call.py
5. Keep your existing actions\__init__.py if you have one.
6. Activate .venv and run:
      cd D:\jarvis-main\jarvis-main
      .\.venv\Scripts\Activate.ps1
      python -c "from actions.whatsapp_desktop_call import whatsapp_desktop_call; print('WHATSAPP IMPORT OK')"
      python main.py

Test phrase:
  Call Ganesh on WhatsApp.

Expected tool route:
  whatsapp_desktop_call {'contact_name': 'Ganesh', 'intent': 'voice_call'}

This fix intentionally does NOT fall back to WhatsApp Web.
It returns success only if it can detect the WhatsApp call UI.
