"""PDF to PLT: Windows GUI and headless conversion entry point."""
import argparse
import math
import os
import queue
import shutil
import sys
import tempfile
import threading
from pathlib import Path

from pdf_to_lasertrace import export, read_logo_pdf

VERSION = '1.0.0'


def convert_pdf(source, output, spacing=.025, overwrite=False):
    source, output = Path(source).resolve(), Path(output).resolve()
    if not source.is_file() or source.suffix.lower() != '.pdf':
        raise ValueError('Sélectionnez un fichier PDF existant.')
    if output.exists() and not output.is_dir():
        raise ValueError('Le dossier de sortie choisi est un fichier.')
    if not math.isfinite(spacing) or spacing < .001:
        raise ValueError('Le pas doit être au moins égal à 0,001 mm.')
    try:
        regions, size = read_logo_pdf(source)
    except (AttributeError, TypeError, IndexError, KeyError, UnicodeError, RecursionError) as error:
        raise ValueError('La structure de ce PDF n’est pas prise en charge.') from error
    output.parent.mkdir(parents=True, exist_ok=True)
    # Finish geometry validation and generation before touching existing outputs.
    with tempfile.TemporaryDirectory(prefix='pdf-to-plt-') as stage:
        export(regions, size, stage, spacing, prefix=source.stem)
        files = sorted(Path(stage).iterdir())
        targets = [output / f.name for f in files]
        if source in targets:
            raise ValueError('Le dossier de sortie ne peut pas écraser le PDF source.')
        if not overwrite and any(f.exists() for f in targets):
            raise FileExistsError('Des fichiers de conversion existent déjà dans ce dossier.')
        if any(f.is_dir() for f in targets):
            raise ValueError('Un sous-dossier porte le nom d’un fichier de sortie.')
        output.mkdir(parents=True, exist_ok=True)
        for source_file, target in zip(files, targets):
            with tempfile.NamedTemporaryFile(dir=output, suffix='.tmp', delete=False) as temporary:
                temp_path = Path(temporary.name)
            try:
                shutil.copyfile(source_file, temp_path)
                temp_path.replace(target)
            finally:
                temp_path.unlink(missing_ok=True)
    return targets, size


def launch_gui(smoke_test=False):
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title(f'PDF to PLT — {VERSION}')
    root.minsize(650, 360)
    root.columnconfigure(0, weight=1)
    frame = ttk.Frame(root, padding=20)
    frame.grid(sticky='nsew')
    frame.columnconfigure(1, weight=1)
    pdf = tk.StringVar()
    destination = tk.StringVar()
    spacing = tk.StringVar(value='0,025')
    status = tk.StringVar(value='Choisissez un PDF vectoriel pour commencer.')
    results = queue.Queue()
    busy = False

    ttk.Label(frame, text='PDF → PLT pour Lasertrace', font=('Segoe UI', 16, 'bold')).grid(
        row=0, column=0, columnspan=3, sticky='w', pady=(0, 8))
    ttk.Label(frame, text='Conserve les contours, les épaisseurs et les extrémités arrondies.').grid(
        row=1, column=0, columnspan=3, sticky='w', pady=(0, 18))

    def select_pdf():
        chosen = filedialog.askopenfilename(title='Choisir le PDF', filetypes=[('PDF vectoriel', '*.pdf')])
        if chosen:
            pdf.set(chosen)
            path = Path(chosen)
            destination.set(str(path.parent / (path.stem + '_PLT')))

    def select_folder():
        chosen = filedialog.askdirectory(title='Choisir le dossier de sortie')
        if chosen:
            destination.set(chosen)

    ttk.Label(frame, text='PDF source').grid(row=2, column=0, sticky='w', padx=(0, 12))
    pdf_entry = ttk.Entry(frame, textvariable=pdf)
    pdf_entry.grid(row=2, column=1, sticky='ew', pady=5)
    pdf_button = ttk.Button(frame, text='Parcourir…', command=select_pdf)
    pdf_button.grid(row=2, column=2, padx=(10, 0))
    ttk.Label(frame, text='Dossier de sortie').grid(row=3, column=0, sticky='w', padx=(0, 12))
    folder_entry = ttk.Entry(frame, textvariable=destination)
    folder_entry.grid(row=3, column=1, sticky='ew', pady=5)
    folder_button = ttk.Button(frame, text='Parcourir…', command=select_folder)
    folder_button.grid(row=3, column=2, padx=(10, 0))
    ttk.Label(frame, text='Pas de remplissage (mm)').grid(row=4, column=0, sticky='w', padx=(0, 12))
    spacing_entry = ttk.Entry(frame, textvariable=spacing, width=12)
    spacing_entry.grid(row=4, column=1, sticky='w', pady=5)
    ttk.Label(frame, text='Le PLT rempli contient les tracés de remplissage.\n'
              'Dans Lasertrace : échelle 1:1, sans ajouter un second remplissage.', wraplength=590).grid(
        row=5, column=0, columnspan=3, sticky='w', pady=(12, 12))

    def set_busy(value):
        nonlocal busy
        busy = value
        for widget in controls:
            widget.configure(state='disabled' if value else 'normal')

    def start_conversion(overwrite=False):
        if not pdf.get().strip() or not destination.get().strip():
            messagebox.showerror('Informations manquantes', 'Choisissez le PDF et le dossier de sortie.')
            return
        try:
            step = float(spacing.get().replace(',', '.'))
            if not math.isfinite(step) or step < .001:
                raise ValueError
        except ValueError:
            messagebox.showerror('Pas invalide', 'Entrez un pas de remplissage d’au moins 0,001 mm.')
            return
        source, output = pdf.get(), destination.get()
        set_busy(True)
        status.set('Conversion en cours…')

        def work():
            try:
                files, size = convert_pdf(source, output, step, overwrite)
                results.put(('success', (files, size)))
            except FileExistsError as error:
                results.put(('exists', str(error)))
            except Exception as error:
                results.put(('error', str(error) or type(error).__name__))
        threading.Thread(target=work, daemon=True).start()

    def poll():
        try:
            kind, value = results.get_nowait()
        except queue.Empty:
            root.after(100, poll)
            return
        set_busy(False)
        if kind == 'success':
            files, size = value
            status.set(f'Terminé : {len(files)} fichiers — page {size[0]:.3f} × {size[1]:.3f} mm.')
            messagebox.showinfo('Conversion terminée',
                                f'Ouvrez dans Lasertrace :\n{next(p.name for p in files if p.name.endswith("_rempli.plt"))}'
                                f'\n\nDossier :\n{files[0].parent}')
        elif kind == 'exists':
            status.set('Les fichiers de sortie existent déjà.')
            if messagebox.askyesno('Remplacer les fichiers ?', value + '\n\nLes remplacer ?'):
                start_conversion(overwrite=True)
        else:
            status.set('La conversion a échoué.')
            messagebox.showerror('Conversion impossible', value)
        root.after(100, poll)

    convert_button = ttk.Button(frame, text='Convertir en PLT', command=start_conversion)
    convert_button.grid(row=6, column=0, columnspan=2, sticky='w', pady=(0, 12))

    def open_folder():
        path = Path(destination.get())
        if destination.get() and path.is_dir():
            if os.name == 'nt':
                os.startfile(path)
            else:
                import webbrowser
                webbrowser.open(path.resolve().as_uri())

    open_button = ttk.Button(frame, text='Ouvrir le dossier', command=open_folder)
    open_button.grid(row=6, column=2, sticky='e', pady=(0, 12))
    ttk.Label(frame, textvariable=status, wraplength=590).grid(
        row=7, column=0, columnspan=3, sticky='w')
    controls = [pdf_entry, folder_entry, spacing_entry, pdf_button, folder_button, convert_button, open_button]

    def close():
        if not busy or messagebox.askyesno('Conversion en cours', 'Fermer et interrompre la conversion ?'):
            root.destroy()
    root.protocol('WM_DELETE_WINDOW', close)
    if smoke_test:
        root.update()
        root.destroy()
    else:
        root.after(100, poll)
        root.mainloop()


def main():
    parser = argparse.ArgumentParser(description='PDF vectoriel → PLT pour Lasertrace')
    parser.add_argument('--version', action='version', version=VERSION)
    parser.add_argument('--convert', type=Path, help='Conversion sans ouvrir la fenêtre')
    parser.add_argument('--output-dir', type=Path, help='Dossier de sortie')
    parser.add_argument('--spacing', type=float, default=.025, help='Pas de remplissage en mm')
    parser.add_argument('--overwrite', action='store_true', help='Remplacer les fichiers de sortie existants')
    parser.add_argument('--smoke-test', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.smoke_test:
        launch_gui(smoke_test=True)
        return 0
    if args.convert:
        output = args.output_dir or args.convert.parent / (args.convert.stem + '_PLT')
        try:
            convert_pdf(args.convert, output, args.spacing, args.overwrite)
        except Exception as error:
            if sys.stderr is not None:
                print(f'Conversion impossible : {error}', file=sys.stderr)
            return 1
    else:
        launch_gui()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
