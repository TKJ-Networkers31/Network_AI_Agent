"""
Entry point alternatif: langsung mulai dengan mode suara aktif,
tapi tetap loop yang sama dengan agent.main (jadi kamu tetap bisa
ketik kapan saja, cuma defaultnya suara sudah ON dari awal).

Jalankan dengan: python -m agent.voice_main
"""

from agent.main import main


if __name__ == "__main__":
    main(start_with_voice=True)