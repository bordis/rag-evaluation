// Configuração de runtime. Fora do container fica vazia e valem os padrões de environment.ts;
// na imagem Docker o nginx responde /env.js com as variáveis do container (docker/nginx.conf.template).
window.__env = {};
