#!/usr/bin/env python3
import sys
import glob
import re
from pathlib import Path

# Comprehensive CID replacement map for PDF font extraction artifacts in normative Markdown
CID_MAP = {
    r'\(cid:32\)': ' = ',
    r'\(cid:33\)': ' = ',
    r'\(cid:14\)': ' + ',
    r'\(cid:16\)': ' - ',
    r'\(cid:152\)': r' \cdot ',
    r'\(cid:117\)': r' \cdot ',
    r'\(cid:35\)': r' \approx ',
    r'\(cid:11\)': '(',
    r'\(cid:12\)': ')',
    r'\(cid:100\)': r' \le ',
    r'\(cid:116\)': r' \ge ',
    r'\(cid:148\)': r' \le ',
    r'\(cid:83\)': r'\pi ',
    r'\(cid:84\)': r'\theta ',
    r'\(cid:73\)': r'\phi ',
    r'\(cid:71\)': r'\Delta ',
    r'\(cid:74\)': r'\gamma ',
    r'\(cid:68\)': r'\Delta ',
    r'\(cid:69\)': r'\beta ',
    r'\(cid:58\)': r'\Omega ',
    r'\(cid:39\)': r'\Delta ',
    r'\(cid:166\)': r'\sum ',
    r'\(cid:167\)': r'\left(',
    r'\(cid:183\)': r'\right)',
    r'\(cid:168\)': r'\left[',
    r'\(cid:184\)': r'\right]',
    r'\(cid:169\)': r'\left\{',
    r'\(cid:185\)': r'\right\}',
    r'\(cid:171\)': r'\left[',
    r'\(cid:187\)': r'\right]',
    r'\(cid:188\)': r'\right]',
    r'\(cid:65\)': r'A',
    r'\(cid:99\)': r'c',
    r'\(cid:120\)': r'x',
}

SQRT_MAP = [
    (r"√f'c", r"$\sqrt{f'_c}$"),
    (r"√f'm", r"$\sqrt{f'_m}$"),
    (r"√Fy", r"$\sqrt{f_y}$"),
    (r"√fy", r"$\sqrt{f_y}$"),
    (r"√f_y", r"$\sqrt{f_y}$"),
    (r"√2", r"$\sqrt{2}$"),
    (r"√𝑡", r"$\sqrt{t}$"),
    (r"√𝑎2+4𝑏2", r"$\sqrt{a^2+4b^2}$"),
]

def fix_units_superscripts(text: str) -> str:
    # Replace unformatted unit superscripts (kgf/cm2, m/s2, m2, etc.)
    text = text.replace('(kgf/cm2)', r'($\text{kgf/cm}^2$)')
    text = text.replace('(kgf/cm²)', r'($\text{kgf/cm}^2$)')
    text = text.replace('(2.5 kgf/cm²)', r'(2.5 $\text{kgf/cm}^2$)')
    text = text.replace('( 1 kgf/cm²)', r'(1 $\text{kgf/cm}^2$)')
    text = text.replace('(0.5 a 1 kgf/cm²)', r'(0.5 a 1 $\text{kgf/cm}^2$)')
    text = text.replace('(0.5 kgf/cm²)', r'(0.5 $\text{kgf/cm}^2$)')
    text = text.replace('kgf/cm2', r'$\text{kgf/cm}^2$')
    text = text.replace('kgf/cm²', r'$\text{kgf/cm}^2$')

    text = text.replace('9.8 m/s²', r'9.8 $\text{m/s}^2$')
    text = text.replace('9.8 m/s2', r'9.8 $\text{m/s}^2$')
    text = text.replace('(m/s²)', r'($\text{m/s}^2$)')
    text = text.replace('(m/s2)', r'($\text{m/s}^2$)')
    text = text.replace('m/s2', r'$\text{m/s}^2$')
    text = text.replace('m/s 2', r'$\text{m/s}^2$')
    text = text.replace('(kg · m/s2)', r'($\text{kg} \cdot \text{m/s}^2$)')
    text = text.replace('(kg \cdot m/s²)', r'($\text{kg} \cdot \text{m/s}^2$)')
    text = text.replace('1 N = 1 kg · 1 m/s 2', r'1 N = 1 $\text{kg} \cdot \text{m/s}^2$')

    text = text.replace('106 g', r'$10^6$ g')
    text = text.replace('en m².', r'en $\text{m}^2$.')
    text = text.replace('m²', r'$\text{m}^2$')
    text = text.replace('$$\\text{m}^2$$', r'$\text{m}^2$')
    return text

def fix_nomenclatura_a2(text: str) -> str:
    # Unicode Greek letters replacements
    text = text.replace('φa', r'$\phi_a$')
    text = text.replace('φp', r'$\phi_p$')
    text = text.replace('φr', r'$\phi_r$')
    text = text.replace('$$\\phi_a$$', r'$\phi_a$')
    text = text.replace('$$\\phi_p$$', r'$\phi_p$')
    text = text.replace('$$\\phi_r$$', r'$\phi_r$')

    # Specific A.2.0 Nomenclatura list headers
    list_headers = [
        'A_a', 'A_v', 'A_d', 'A_e', 'A_t', 'F_a', 'F_v', 'F_s', 'S_a', 'S_d', 'S_v',
        'T_0', 'T_C', 'T_L', 'R_0', 'R', 'R_Capr0', 'I_e', 'I', 'IP', 'd_c', 'd_i', 'd_s',
        'g', 'H_c', 'N_i', 's_ui', 'v_si', 'w'
    ]
    for s in list_headers:
        text = text.replace(f'**{s}** =', f'**${s}$** =')

    text = text.replace('- **$R_Capr0$** =', '- **$R_{\\text{Capr0}}$** =')
    text = text.replace('- **$IP$** =', '- **$\\text{IP}$** =')
    text = text.replace('- **$s_ui$** =', '- **$s_{ui}$** =')
    text = text.replace('- **$v_si$** =', '- **$v_{si}$** =')
    text = text.replace('$s_ui$', '$s_{ui}$')
    text = text.replace('$v_si$', '$v_{si}$')

    # Subscripts and in-line variables in Nomenclature
    text = text.replace('los k estratos', 'los $k$ estratos')
    text = text.replace('los m estratos', 'los $m$ estratos')
    text = text.replace('estrato i', 'estrato $i$')
    text = text.replace('energía N60.', 'energía $N_{60}$.')
    text = text.replace('El valor de N_i usado', 'El valor de $N_i$ usado')
    text = text.replace('función del valor de R,', 'función del valor de $R$,')
    text = text.replace('período de vibración T.', 'período de vibración $T$.')
    text = text.replace('R = $\\phi_a$ · $\\phi_p$ · $\\phi_r$ · $R_0$', r'$R = \phi_a \cdot \phi_p \cdot \phi_r \cdot R_0$')

    return text

def fix_normative_equations(text: str) -> str:
    # Fix broken ( R = \phi_a\phi_p\phi_r R ) .
    text = re.sub(r'\(\s*R\s*=\s*\$\\phi_a\$\s*\\phi_p\s*\$\\phi_r\$\s*R\s*\)\s*\.', r'($R = \\phi_a \\cdot \\phi_p \\cdot \\phi_r \\cdot R_0$)', text)
    text = re.sub(r'\(\s*R\s*=\s*\$\\phi_a\$\s*\$\\phi_p\$\s*\$\\phi_r\$\s*R\s*\)\s*\.', r'($R = \\phi_a \\cdot \\phi_p \\cdot \\phi_r \\cdot R_0$)', text)

    # A.3.6-2
    text = re.sub(
        r'multiplicándola por un coeficiente de amplificación,\s*A\s*x\s*,\s*determinado de acuerdo con la siguiente ecuación:\s*\\Delta max A x = \\left\[ \\left\[ 1\.2\\Delta prom\\right\]\\right\] 2 \\right\] \\le 3\.0 \(A\.3\.6-2\)',
        r'multiplicándola por un coeficiente de amplificación, $A_x$, determinado de acuerdo con la siguiente ecuación:\n\n$$A_x = \\left[ \\frac{\\delta_{\\max}}{1.2 \\delta_{\\text{prom}}} \\right]^2 \\le 3.0 \\quad \\text{(A.3.6-2)}$$',
        text
    )

    # A.3.6-3
    text = re.sub(
        r'\(S - A \)h a = A \+ a a = S i h eq puede estimarse simplificadamente como 0\.75h n s i h \\le h s h i eq \(A\.3\.6-3\) h \\ge h ah i eq',
        r'$$a_i = A_a + (S_a - A_a) \\frac{h_i}{h_{\\text{eq}}} \\quad \\text{(A.3.6-3)}$$',
        text
    )

    # A.4.2-1 & A.4.2-2
    text = re.sub(
        r'n \( \\sum m i\$\\Delta_i\$ T = 2\\pi i = 1 \\sum \(f i\$\\Delta_i\$ \) i = 1 2\) \(A\.4\.2-1\)',
        r'\n\n$$T = 2\\pi \\sqrt{\\frac{\\sum_{i=1}^{n} m_i \\Delta_i^2}{\\sum_{i=1}^{n} f_i \\Delta_i}} \\quad \\text{(A.4.2-1)}$$\n\n',
        text
    )
    text = re.sub(
        r'C u = 1\.75 - 1\.2A v F v pero C u no debe ser menor de 1\.2\. \(A\.4\.2-2\)',
        r'\n\n$$C_u = 1.75 - 1.2 A_v F_v \\ge 1.2 \\quad \\text{(A.4.2-2)}$$',
        text
    )

    # A.4.2-3
    text = re.sub(
        r'T = C h \\Delta donde C t y \\Delta tienen los valores dados en la tabla A\.4\.2-1\. Tabla A\.4\.2-1 \(A\.4\.2-3\)',
        r'\n\n$$T_a = C_t h^\\alpha \\quad \\text{(A.4.2-3)}$$\n\ndonde $C_t$ y $\\alpha$ tienen los valores dados en la tabla A.4.2-1.',
        text
    )

    # A.4.2-4
    text = re.sub(
        r'C = w A B i = 1\\left\[\\left\{ wi \\right\} \\left\[\s*<!-- /CHUNK -->.*?<!-- CHUNK.*?-->.*?2 \\right\]\s*A wi \\right\] \\cdot \\sum \\left\[\\left\[ n \\right\] \\right\] \(A\.4\.2-4\) h 2 \\left\(h wi \\right\) \\right\] 1 \+ 0\.83\\left\[ \\right\] \\right\] \\left\{Awi \\right\} \\right\]\\right\]',
        r'$$C_t = \\frac{0.0062}{\\sqrt{C_w}} \\quad \\text{(A.4.2-4)}$$',
        text,
        flags=re.DOTALL
    )

    # A.4.2-5
    text = text.replace(r'T a = 0.1N (A.4.2-5)', r'$$T_a = 0.1N \quad \text{(A.4.2-5)}$$')

    # A.4.3-1
    text = text.replace(r'se obtiene por medio de la siguiente ecuación: V s = S a g M (A.4.3-1)', r'se obtiene por medio de la siguiente ecuación:\n\n$$V_s = S_a g M \quad \text{(A.4.3-1)}$$')

    # A.4.3-2 & A.4.3-3
    text = text.replace(
        r'debe determinarse usando la siguiente ecuación: F x = C vx V s m h k C = ( m h i = 1 (A.4.3-2) x x (A.4.3-3) n k) i i',
        r'debe determinarse usando la siguiente ecuación:\n\n$$F_x = C_{vx} V_s \quad \text{(A.4.3-2)}$$\n\n$$C_{vx} = \frac{m_x h_x^k}{\sum_{i=1}^{n} m_i h_i^k} \quad \text{(A.4.3-3)}$$'
    )

    # A.5.4-1 & A.5.4-2
    text = re.sub(
        r'M j = \\sum M mj \\ge 0\.90 M m = 1 \\left\( n \\left\[ \\sum m i\\phi m \\right\] m \( \\phi \\sum i ij i = 1 \(A\.5\.4-1\) \\right\) 2 ij \\right\] = \\left\{i = 1 \\right\} \(A\.5\.4-2\) n m\)2',
        r'$$M_j = \\sum_{m=1}^{p} M_{mj} \\ge 0.90 M \\quad \\text{(A.5.4-1)}$$\n\n$$M_{mj} = \\frac{\\left[ \\sum_{i=1}^{n} m_i \\phi_{ijm} \\right]^2}{\\sum_{i=1}^{n} m_i \\phi_{ijm}^2} \\quad \\text{(A.5.4-2)}$$',
        text
    )

    # A.5.4-3
    text = text.replace(r'V mj = S am gM mj (A.5.4-3)', r'$$V_{mj} = S_{am} g M_{mj} \quad \text{(A.5.4-3)}$$')

    # A.5.4-4 & A.5.4-5
    text = text.replace(r'0.80 V tj para estructuras regulares (A.5.4-4)', r'$$V_t \ge 0.80 V_s \quad \text{para estructuras regulares} \quad \text{(A.5.4-4)}$$')
    text = text.replace(r'0.90 V tj para estructuras irregulares (A.5.4-5)', r'$$V_t \ge 0.90 V_s \quad \text{para estructuras irregulares} \quad \text{(A.5.4-5)}$$')

    # A.6.2-1
    text = text.replace(r'$\Delta_t$,j = r j\theta i (A.6.2-1)', r'$$\Delta_{t,j} = r_j \theta_i \quad \text{(A.6.2-1)}$$')

    # A.6.2-2
    text = text.replace(r'P i\Delta cm Q i = Vh i pi (A.6.2-2)', r'$$Q_i = \frac{P_i \Delta_{\text{cm}}}{V_i h_{pi}} \quad \text{(A.6.2-2)}$$')

    # A.6.2-3
    text = re.sub(
        r'\\left\( Q i \\right\) \\Delta pd = \\Delta cm\\left\[ \\left\{ 1 - Q i \\right\} \\right\] \(A\.6\.2-3\)',
        r'$$\\Delta_{pd} = \\Delta_{\\text{cm}} \\left[ \\frac{Q_i}{1 - Q_i} \\right] \\quad \\text{(A.6.2-3)}$$',
        text
    )

    # A.6.2-4
    text = text.replace(r'\Delta t0t,j = \Delta cm,j + $\Delta_t$,j + \Delta pd,j (A.6.2-4)', r'$$\Delta_{\text{tot},j} = \Delta_{\text{cm},j} + \Delta_{t,j} + \Delta_{pd,j} \quad \text{(A.6.2-4)}$$')

    # A.8.2-1 & A.8.2-2
    text = re.sub(
        r'\(S - A \)h a = A \+ a a = S i h eq puede estimarse simplificadamente como 0\.75h n s i h \\le h s h i eq \(A\.8\.2-1\) h \\ge h ah i eq',
        r'$$a_i = A_a + (S_a - A_a) \\frac{h_i}{h_{\\text{eq}}} \\quad \\text{(A.8.2-1)}$$',
        text
    )
    text = text.replace(r'a x g F p = R 0 M p (A.8.2-2)', r'$$F_p = \frac{a_x g M_p}{R_0} \quad \text{(A.8.2-2)}$$')

    # A.9.4-1 & A.9.4-2
    text = re.sub(
        r'a x a p F = A I gM \\ge a gM \(A\.9\.4-1\) R p 2 p',
        r'$$F_p = \\frac{a_x a_p A_I g M_p}{R_p} \\ge 0.4 A_a I_g M_p \\quad \\text{(A.9.4-1)}$$',
        text
    )
    text = re.sub(
        r'\(S - A \)h a = A \+ a a = S x h eq puede estimarse simplificadamente como 0\.75h n \. s x h \\le h s h x eq \(A\.9\.4-2\) h \\ge h ah x eq',
        r'$$a_x = A_a + (S_a - A_a) \\frac{h_x}{h_{\\text{eq}}} \\quad \\text{(A.9.4-2)}$$',
        text
    )

    # A.12.3-1 to A.12.3-6
    text = text.replace(r'#### A.12.3.2 — a A.12.3.4. 1.5A d S S ad = (A.12.3-1)', r'$$S_{ad} = \frac{1.5 A_d S}{T} \quad \text{(A.12.3-1)}$$')
    text = text.replace(r'S = A (1.0 + 8T) (A.12.3-2)', r'$$S_{ad} = A_d (1.0 + 8T) \quad \text{(A.12.3-2)}$$')
    text = text.replace(r'T Cd = 0.5S S ad = 3.0A d (A.12.3-3) (A.12.3-4)', r'$$T_{Cd} = 0.5 S \quad \text{(A.12.3-3)}$$\n\n$$S_{ad} = 3.0 A_d \quad \text{(A.12.3-4)}$$')
    text = re.sub(r'0\.25s T Cd = 0\.5S \(A\.12\.3-5\) \(A\.12\.3-6\)', r'$$T_{Ld} = 2.4 S \\quad \\text{(A.12.3-5)}$$\n\n$$S_{ad} = \\frac{1.5 A_d S T_{Ld}}{T^2} \\quad \\text{(A.12.3-6)}$$', text)

    return text

def fix_equations_content(text: str) -> str:
    # 0. Fix normative display equations
    text = fix_normative_equations(text)

    # 1. Replace all CID codes using lambda to avoid escape errors
    for cid_pattern, replacement in CID_MAP.items():
        text = re.sub(cid_pattern, lambda m, r=replacement: r, text)

    # 2. Replace unicode square roots
    for orig, repl in SQRT_MAP:
        text = text.replace(orig, repl)

    # 3. Post-process Greek and symbol space-separated subscripts
    text = re.sub(r'\\phi\s*([apr])\b', lambda m: f"$\\phi_{m.group(1)}$", text)
    text = re.sub(r'\\Omega\s*0\b', lambda m: r"$\Omega_0$", text)
    text = re.sub(r'\\Delta\s*([0-9a-z])\b', lambda m: f"$\\Delta_{m.group(1)}$", text)

    # 4. Fix unit superscripts
    text = fix_units_superscripts(text)

    # 5. Fix nomenclature A.2.0 items
    text = fix_nomenclatura_a2(text)

    # 6. Clean up generic remnant (cid:XXX) if any
    text = re.sub(r'\(cid:\d+\)', '', text)

    # 7. Clean up duplicate spaces
    text = re.sub(r' +', ' ', text)

    return text

def process_file(file_path: str, start_line: int = 1):
    path = Path(file_path)
    if not path.exists():
        print(f"File not found: {file_path}")
        return
    
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    header = "".join(lines[:start_line - 1])
    body = "".join(lines[start_line - 1:])

    fixed_body = fix_equations_content(body)
    fixed = header + fixed_body

    if "".join(lines) != fixed:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(fixed)
        print(f"Successfully fixed equations in {file_path} (from line {start_line})")
    else:
        print(f"No changes required for {file_path}")

def main():
    start_line = 1
    args = sys.argv[1:]
    if '--start-line' in args:
        idx = args.index('--start-line')
        start_line = int(args[idx + 1])
        args = args[:idx] + args[idx + 2:]

    if len(args) > 0:
        for arg in args:
            for f in glob.glob(arg):
                process_file(f, start_line=start_line)
    else:
        print("Uso: python3 corregir_ecuaciones.py archivo.md [más.md ...] [--start-line N]")
        sys.exit(1)

if __name__ == '__main__':
    main()
