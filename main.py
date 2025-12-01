import anthropic
import os
import urllib.request
import urllib.parse
import json
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

# === FONCTIONS FICHIERS ===

def lire_fichier(chemin):
    try:
        with open(chemin, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return ""

def ecrire_fichier(chemin, contenu):
    with open(chemin, 'w', encoding='utf-8') as f:
        f.write(contenu)

def ajouter_fichier(chemin, contenu):
    with open(chemin, 'a', encoding='utf-8') as f:
        f.write(contenu)

# === FONCTION EMAIL ===

def envoyer_email(destinataire, sujet, corps):
    """Envoie un email via Gmail"""
    try:
        gmail_user = os.environ.get("GMAIL_USER")
        gmail_password = os.environ.get("GMAIL_APP_PASSWORD")
        
        if not gmail_user or not gmail_password:
            return False, "Configuration email manquante"
        
        msg = MIMEMultipart()
        msg['From'] = gmail_user
        msg['To'] = destinataire
        msg['Subject'] = sujet
        msg.attach(MIMEText(corps, 'plain', 'utf-8'))
        
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(gmail_user, gmail_password)
        server.sendmail(gmail_user, destinataire, msg.as_string())
        server.quit()
        
        return True, "Email envoyé"
    except Exception as e:
        return False, str(e)

# === FONCTION RECHERCHE WEB ===

def rechercher_web(query, max_results=3):
    """Recherche sur DuckDuckGo"""
    try:
        query_encoded = urllib.parse.quote(query)
        url = f"https://html.duckduckgo.com/html/?q={query_encoded}"
        
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode('utf-8')
        
        results = []
        pattern = r'<a class="result__a" href="([^"]+)"[^>]*>([^<]+)</a>'
        matches = re.findall(pattern, html)
        
        for url, title in matches[:max_results]:
            if url.startswith('//'):
                url = 'https:' + url
            results.append(f"- {title.strip()}: {url}")
        
        return "\n".join(results) if results else "Aucun résultat"
    except Exception as e:
        return f"Erreur recherche: {e}"

# === FONCTION CRÉATION DOCUMENT ===

def creer_document(nom_fichier, contenu):
    """Crée un document téléchargeable"""
    try:
        chemin = f"/tmp/{nom_fichier}"
        with open(chemin, 'w', encoding='utf-8') as f:
            f.write(contenu)
        return True, nom_fichier
    except Exception as e:
        return False, str(e)

# === GÉNÉRATION RÉPONSE ===

def generer_reponse(client, message, identite, histoire, conversations):
    """Génère une réponse via Claude - Style direct et concis"""
    
    projets = lire_fichier("projets.txt")
    decisions = lire_fichier("decisions.txt")
    idees = lire_fichier("idees.txt")
    
    system_prompt = f"""Tu es Axis, assistant opérationnel pour Anthony et les agences Ici Dordogne.

RÈGLES ABSOLUES:
1. Réponses COURTES et DIRECTES. Pas de bavardage.
2. Va droit au but. Pas d'introduction, pas de conclusion polie.
3. Si tu ne sais pas, dis "Je ne sais pas" et c'est tout.
4. Liste les étapes si c'est une procédure, sinon phrases courtes.
5. Pas d'émojis, pas de formules de politesse.

{identite}

CONTEXTE AGENCES:
{projets}

DÉCISIONS PASSÉES:
{decisions}

ÉCHANGES RÉCENTS:
{conversations}

CAPACITÉS (utilise si pertinent):
- [RECHERCHE: terme] pour chercher sur le web
- [EMAIL: destinataire | sujet | contenu] pour envoyer un email
- [DOCUMENT: nom.txt | contenu] pour créer un fichier
- [MÉMOIRE: projets/decisions/idees | texte à ajouter] pour noter quelque chose"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        system=system_prompt,
        messages=[{"role": "user", "content": message}]
    )
    
    reponse_texte = response.content[0].text
    
    # Traitement des commandes
    if "[RECHERCHE:" in reponse_texte:
        match = re.search(r'\[RECHERCHE:\s*([^\]]+)\]', reponse_texte)
        if match:
            terme = match.group(1).strip()
            resultats = rechercher_web(terme)
            reponse_texte = reponse_texte.replace(match.group(0), f"Résultats:\n{resultats}")
    
    if "[EMAIL:" in reponse_texte:
        match = re.search(r'\[EMAIL:\s*([^|]+)\|([^|]+)\|([^\]]+)\]', reponse_texte)
        if match:
            dest, sujet, corps = match.group(1).strip(), match.group(2).strip(), match.group(3).strip()
            succes, msg = envoyer_email(dest, sujet, corps)
            status = "Email envoyé." if succes else f"Échec: {msg}"
            reponse_texte = reponse_texte.replace(match.group(0), status)
    
    if "[DOCUMENT:" in reponse_texte:
        match = re.search(r'\[DOCUMENT:\s*([^|]+)\|([^\]]+)\]', reponse_texte, re.DOTALL)
        if match:
            nom, contenu = match.group(1).strip(), match.group(2).strip()
            succes, result = creer_document(nom, contenu)
            status = f"Document créé: {nom}" if succes else f"Échec: {result}"
            reponse_texte = reponse_texte.replace(match.group(0), status)
    
    if "[MÉMOIRE:" in reponse_texte:
        match = re.search(r'\[MÉMOIRE:\s*([^|]+)\|([^\]]+)\]', reponse_texte)
        if match:
            type_mem, contenu = match.group(1).strip(), match.group(2).strip()
            fichier_map = {"projets": "projets.txt", "decisions": "decisions.txt", "idees": "idees.txt"}
            if type_mem in fichier_map:
                ajouter_fichier(fichier_map[type_mem], f"\n{contenu}")
                reponse_texte = reponse_texte.replace(match.group(0), "Noté.")
    
    return reponse_texte

# === GÉNÉRATION PAGE HTML ===

def generer_page_html(conversations_html, documents=None):
    """Page web épurée pour Anthony"""
    
    docs_html = ""
    if documents:
        docs_html = "<div class='docs'><strong>Documents:</strong> "
        docs_html += " | ".join([f"<a href='/download/{d}'>{d}</a>" for d in documents])
        docs_html += "</div>"
    
    return f'''<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Axis - Ici Dordogne</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #1a1a2e; 
            color: #eee;
            min-height: 100vh;
        }}
        .container {{ max-width: 900px; margin: 0 auto; padding: 20px; }}
        
        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 15px 0;
            border-bottom: 1px solid #333;
            margin-bottom: 20px;
        }}
        .logo {{ font-size: 1.5em; font-weight: bold; color: #4a9eff; }}
        .actions a {{
            color: #888;
            text-decoration: none;
            margin-left: 15px;
            font-size: 0.9em;
        }}
        .actions a:hover {{ color: #fff; }}
        
        .messages {{
            height: calc(100vh - 250px);
            overflow-y: auto;
            padding: 10px 0;
        }}
        .message {{
            padding: 12px 15px;
            margin: 8px 0;
            border-radius: 8px;
            max-width: 85%;
        }}
        .message-user {{
            background: #2d2d44;
            margin-left: auto;
        }}
        .message-axis {{
            background: #16213e;
            border-left: 3px solid #4a9eff;
        }}
        .message-header {{
            font-size: 0.75em;
            color: #666;
            margin-bottom: 5px;
        }}
        .message-time {{
            font-size: 0.7em;
            color: #555;
            margin-top: 8px;
        }}
        
        .input-zone {{
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background: #1a1a2e;
            padding: 15px;
            border-top: 1px solid #333;
        }}
        .input-zone form {{
            max-width: 900px;
            margin: 0 auto;
            display: flex;
            gap: 10px;
        }}
        textarea {{
            flex: 1;
            background: #2d2d44;
            border: 1px solid #444;
            color: #fff;
            padding: 12px;
            border-radius: 8px;
            resize: none;
            font-size: 1em;
            min-height: 50px;
        }}
        textarea:focus {{ outline: none; border-color: #4a9eff; }}
        button {{
            background: #4a9eff;
            color: #fff;
            border: none;
            padding: 12px 25px;
            border-radius: 8px;
            cursor: pointer;
            font-weight: bold;
        }}
        button:hover {{ background: #3a8eef; }}
        
        .memory-buttons {{
            display: flex;
            gap: 10px;
            margin-top: 10px;
        }}
        .memory-btn {{
            background: #2d2d44;
            color: #888;
            padding: 8px 15px;
            border-radius: 5px;
            text-decoration: none;
            font-size: 0.85em;
        }}
        .memory-btn:hover {{ background: #3d3d54; color: #fff; }}
        
        .docs {{
            background: #16213e;
            padding: 10px 15px;
            border-radius: 5px;
            margin-bottom: 15px;
            font-size: 0.9em;
        }}
        .docs a {{ color: #4a9eff; }}
        
        .empty {{
            text-align: center;
            color: #666;
            padding: 50px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="logo">Axis</div>
            <div class="actions">
                <a href="/export">Export</a>
                <a href="/effacer" onclick="return confirm('Effacer?')">Effacer</a>
            </div>
        </header>
        
        {docs_html}
        
        <div class="messages" id="messages">
            {conversations_html}
        </div>
    </div>
    
    <div class="input-zone">
        <form action="/chat" method="POST">
            <textarea name="message" placeholder="Message..." rows="2" 
                onkeydown="if(event.ctrlKey && event.key==='Enter')this.form.submit()"></textarea>
            <button type="submit">Envoyer</button>
        </form>
        <div class="memory-buttons" style="max-width:900px;margin:10px auto 0;">
            <a href="/memoire/projets" target="_blank" class="memory-btn">Projets</a>
            <a href="/memoire/decisions" target="_blank" class="memory-btn">Décisions</a>
            <a href="/memoire/idees" target="_blank" class="memory-btn">Idées</a>
        </div>
    </div>
    
    <script>
        document.getElementById('messages').scrollTop = document.getElementById('messages').scrollHeight;
    </script>
</body>
</html>'''

def formater_conversations_html(conversations_txt):
    """Formate les conversations en HTML"""
    if not conversations_txt.strip():
        return '<div class="empty">Prêt.</div>'
    
    html = ""
    blocs = conversations_txt.split("========================================")
    
    for bloc in blocs:
        if not bloc.strip():
            continue
            
        date_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', bloc)
        date_str = date_match.group(1) if date_match else ""
        
        if "[ANTHONY]" in bloc:
            parties = bloc.split("[ANTHONY]")
            if len(parties) > 1:
                contenu = parties[1].split("[AXIS]")[0].strip()
                if contenu:
                    contenu_html = contenu.replace('<', '&lt;').replace('>', '&gt;')
                    html += f'''<div class="message message-user">
                        <div class="message-header">Anthony</div>
                        {contenu_html}
                        <div class="message-time">{date_str}</div>
                    </div>'''
        
        if "[AXIS]" in bloc:
            parties = bloc.split("[AXIS]")
            if len(parties) > 1:
                contenu = parties[1].strip()
                if contenu:
                    contenu = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', contenu)
                    contenu_html = contenu.replace('\n', '<br>')
                    html += f'''<div class="message message-axis">
                        <div class="message-header">Axis</div>
                        {contenu_html}
                        <div class="message-time">{date_str}</div>
                    </div>'''
    
    return html if html else '<div class="empty">Prêt.</div>'

def get_documents_disponibles():
    """Liste les documents dans /tmp"""
    docs = []
    try:
        for f in os.listdir('/tmp'):
            if f.endswith(('.txt', '.md', '.csv', '.json', '.docx')):
                docs.append(f)
    except:
        pass
    return docs

# === SERVEUR HTTP ===

class AxisHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            conversations_txt = lire_fichier("conversations.txt")
            conversations_html = formater_conversations_html(conversations_txt)
            docs = get_documents_disponibles()
            html = generer_page_html(conversations_html, docs if docs else None)
            
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html.encode('utf-8'))
        
        elif self.path.startswith('/memoire/'):
            type_memoire = self.path.split('/')[-1]
            fichier = f"{type_memoire}.txt"
            contenu = lire_fichier(fichier)
            
            self.send_response(200)
            self.send_header('Content-type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(contenu.encode('utf-8'))
        
        elif self.path == '/export':
            conversations = lire_fichier("conversations.txt")
            
            self.send_response(200)
            self.send_header('Content-type', 'text/plain; charset=utf-8')
            self.send_header('Content-Disposition', 'attachment; filename="conversations_axis.txt"')
            self.end_headers()
            self.wfile.write(conversations.encode('utf-8'))
        
        elif self.path == '/effacer':
            ecrire_fichier("conversations.txt", "")
            
            self.send_response(303)
            self.send_header('Location', '/')
            self.end_headers()
        
        elif self.path.startswith('/download/'):
            filename = self.path.split('/')[-1]
            filepath = f"/tmp/{filename}"
            
            if os.path.exists(filepath):
                with open(filepath, 'rb') as f:
                    contenu = f.read()
                
                self.send_response(200)
                self.send_header('Content-type', 'application/octet-stream')
                self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
                self.end_headers()
                self.wfile.write(contenu)
            else:
                self.send_response(404)
                self.end_headers()
        
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_POST(self):
        if self.path == "/chat":
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length).decode('utf-8')
            
            params = urllib.parse.parse_qs(post_data)
            message = params.get('message', [''])[0]
            
            if message.strip():
                print(f"[MSG] {message[:50]}...")
                
                identite = lire_fichier("identite.txt")
                histoire = lire_fichier("histoire.txt")
                conversations = lire_fichier("conversations.txt")
                
                conversations_contexte = "\n".join(conversations.split("========================================")[-20:])
                
                try:
                    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
                    reponse = generer_reponse(client, message, identite, histoire, conversations_contexte)
                    print(f"[REP] {reponse[:50]}...")
                except Exception as e:
                    print(f"[ERR] {e}")
                    reponse = f"Erreur: {e}"
                
                maintenant = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                echange = f"""
========================================
{maintenant}
========================================

[ANTHONY]
{message}

[AXIS]
{reponse}
"""
                ajouter_fichier("conversations.txt", echange)
            
            self.send_response(303)
            self.send_header('Location', '/')
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {args[0]}")

# === MAIN ===

def main():
    print("=" * 40)
    print("AXIS - ICI DORDOGNE")
    print("=" * 40)
    
    fichiers_defaut = {
        "identite.txt": "Assistant Ici Dordogne",
        "histoire.txt": "",
        "conversations.txt": "",
        "projets.txt": "",
        "decisions.txt": "",
        "idees.txt": ""
    }
    
    for fichier, contenu_defaut in fichiers_defaut.items():
        if not os.path.exists(fichier):
            ecrire_fichier(fichier, contenu_defaut)
    
    port = int(os.environ.get("PORT", 8080))
    serveur = HTTPServer(('0.0.0.0', port), AxisHandler)
    print(f"Port: {port}")
    print("Prêt.")
    serveur.serve_forever()

if __name__ == "__main__":
    main()
