"""Typer-based Command Line Interface for AIRA."""

import typer
from rich.console import Console

from aira.app import AIRAApplication

app = typer.Typer(help="AIRA - Artificial Intelligent Responsive Assistant CLI Manager")
console = Console()


@app.command()
def start() -> None:
    """Boot the system and enter interactive console mode."""
    aira_app = AIRAApplication()
    aira_app.start()
    aira_app.run_interactive()


@app.command()
def status() -> None:
    """Run baseline health checks and output system diagnostics."""
    aira_app = AIRAApplication()
    try:
        # Run bootstrap checks
        aira_app.start()
        console.print("[bold green]✔ All system parameters are healthy.[/bold green]")
    except Exception as e:
        console.print(f"[bold red]❌ Health Check Failed: {e}[/bold red]")
    finally:
        aira_app.stop()


@app.command()
def voice_demo() -> None:
    """Run an interactive demonstration of the integrated Voice Platform pipeline."""
    console.print("[bold cyan]====================================================[/bold cyan]")
    console.print("[bold cyan]       AIRA Integrated Voice Platform Demo          [/bold cyan]")
    console.print("[bold cyan]====================================================[/bold cyan]")

    aira_app = AIRAApplication()
    try:
        # 1. Initialize
        aira_app.start()

        # Verify components
        assert aira_app.voice_session is not None
        assert aira_app.intent is not None
        assert aira_app.request_normalization is not None
        assert aira_app.speech_recognition is not None

        console.print("\n[bold yellow]AIRA > Waiting for Wake Word...[/bold yellow]")
        console.print("[dim](Simulating raw audio stream matching configured triggers)[/dim]")

        # Start Voice Session
        aira_app.voice_session.start_session()
        active_sess = aira_app.voice_session.active_session
        assert active_sess is not None

        # Process wake trigger
        wake_chunk = b"HEY_AIRA_TRIGGER"
        console.print('\n[green]User spoke:[/green] [italic]"Hey AIRA"[/italic]')

        aira_app.voice_session.process_audio(wake_chunk)
        console.print("[bold green]✔ Wake Detected & Confirmed[/bold green]")
        console.print("[bold yellow]AIRA > Listening & Recognizing...[/bold yellow]")

        # Simulate STT translation chunk
        audio_chunk = b"DEMO_OPEN_SAFARI"
        console.print('\n[green]User spoke:[/green] [italic]"open safari"[/italic]')

        # Transcribe through STT inside Session
        result = aira_app.speech_recognition.transcribe_audio(audio_chunk)
        console.print(f'[bold green]✔ Transcription Finished:[/bold green] "{result.text}"')

        # Run Intent Layer
        intent_res = aira_app.intent.recognize_intent(result.text, active_sess.session_id)
        console.print(
            f"[bold green]✔ Intent Classifier Matched:[/bold green] {intent_res.intent_name}"
        )
        console.print(f"[bold green]✔ Extracted Parameters:[/bold green] {intent_res.parameters}")

        # Run Request Normalizer
        request_res = aira_app.request_normalization.create_request(intent_res)
        console.print("[bold green]✔ Runtime Request Schema Generated Successfully:[/bold green]")

        import json

        console.print_json(json.dumps(request_res.to_dict()))

        # Finalize Session
        aira_app.voice_session.close_session()
        console.print("\n[bold green]✔ Demo Finished Successfully[/bold green]")

    except Exception as e:
        console.print(f"[bold red]❌ Voice Demo Pipeline Failed: {e}[/bold red]")
    finally:
        aira_app.stop()


if __name__ == "__main__":
    app()
