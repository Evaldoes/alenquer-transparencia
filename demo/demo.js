// Demonstração estática: responde às chamadas da API com dados fictícios, sem rede nem servidor.
(() => {
  const empresa = (nome, objeto, score, flags, modalidade, valor, capital, inicio, porte) => ({
    score, nivel: '', icone: score >= 70 ? '🔴' : score >= 40 ? '🟡' : '🟢', flags,
    conflitos: [], sancoes: { ceis: [], cnep: [] }, analisado_em: '2026-11-02T10:00:00',
    contrato: { nomeContratado: nome, objetoCompra: objeto, modalidadeCompra: modalidade, valor },
    cnpj_dados: { capital, inicio, porte, socios: [] },
  });
  const ALFA = 'Empresa Exemplo Alfa LTDA';
  const BETA = 'Construtora Fictícia Beta S.A.';
  const GAMA = 'Serviços Modelo Gama LTDA';
  const DELTA = 'Comércio Ilustrativo Delta ME';
  const OBJETO = 'Aquisição de material de escritório para a secretaria municipal';
  const DADOS = {
    '/api/token': { token: '' },
    '/api/noticias': [],
    '/api/monitor': [
      empresa(ALFA, OBJETO, 75, ['Empresa com menos de 3 meses de existência', 'Capital social baixo (R$ 5.000)', 'Contratação sem licitação (dispensa/inexigibilidade)'], 'Dispensa', 48000, 5000, '2026-09-01', 'Microempresa'),
      empresa(BETA, 'Reforma de escola municipal', 45, ['Mesma empresa aparece em 3 contratos', 'Preço 62% acima da média'], 'Pregão', 312000, 800000, '2015-03-12', 'Demais'),
      empresa(DELTA, OBJETO, 40, ['Contratação sem licitação (dispensa/inexigibilidade)', 'Capital social baixo (R$ 8.000)'], 'Dispensa', 21000, 8000, '2019-02-10', 'Microempresa'),
      empresa(GAMA, 'Manutenção de equipamentos de informática', 15, ['Mesma empresa aparece em 3 contratos'], 'Pregão', 27500, 150000, '2011-06-20', 'Pequeno porte'),
    ],
    '/api/historico': [
      { data: '2026-11-02', alto_risco: 1, medio_risco: 2 },
      { data: '2026-10-05', alto_risco: 2, medio_risco: 1 },
      { data: '2026-09-07', alto_risco: 1, medio_risco: 1 },
    ],
    '/api/copypaste': {
      clusters: [[ALFA, DELTA]],
      pares: [{ similaridade: 96, objeto_a: OBJETO, objeto_b: OBJETO, contrato_a: { nomeContratado: ALFA }, contrato_b: { nomeContratado: DELTA } }],
    },
    '/api/empresas/resumo': { total_empresas: 4, alto_risco: 1, em_alta: 1 },
    '/api/empresas/em-alta': [{ nome: ALFA, score_max: 75, aparicoes: 2, primeira_vez: '2026-10-05', delta: 20 }],
    '/api/empresas/ranking': [
      { nome: ALFA, score_medio: 65, score_max: 75, tendencia: 'subindo' },
      { nome: BETA, score_medio: 45, score_max: 45, tendencia: 'estável' },
      { nome: DELTA, score_medio: 38, score_max: 40, tendencia: 'estável' },
      { nome: GAMA, score_medio: 15, score_max: 15, tendencia: 'descendo' },
    ],
    '/api/grafo': {
      metricas: { total_nos: 5, empresas: 4, pessoas: 1, grupos: 1 },
      nodes: [
        { id: 1, label: ALFA, color: '#fca5a5' }, { id: 2, label: BETA, color: '#fcd34d' },
        { id: 3, label: DELTA, color: '#fcd34d' }, { id: 4, label: GAMA, color: '#86efac' },
        { id: 5, label: 'Sócio fictício', shape: 'box' },
      ],
      edges: [{ from: 1, to: 5 }, { from: 3, to: 5 }, { from: 1, to: 3, label: 'objeto similar' }],
    },
  };
  const responder = (corpo, status = 200) => new Response(JSON.stringify(corpo), {
    status, headers: { 'Content-Type': 'application/json' },
  });
  const fetchReal = window.fetch.bind(window);
  window.fetch = async (entrada, opcoes = {}) => {
    const caminho = new URL(typeof entrada === 'string' ? entrada : entrada.url, location.href).pathname;
    if (!caminho.startsWith('/api/')) return fetchReal(entrada, opcoes);
    const metodo = (opcoes.method || 'GET').toUpperCase();
    if (metodo === 'GET' && caminho in DADOS) return responder(DADOS[caminho]);
    return responder({ erro: 'Indisponível na demonstração.' }, 403);
  };

  const ABAS = ['risco', 'copypaste', 'empresas', 'grafo'];
  document.addEventListener('DOMContentLoaded', () => {
    const faixa = document.createElement('div');
    faixa.setAttribute('role', 'note');
    faixa.style.cssText = 'position:fixed;left:0;right:0;bottom:0;z-index:9999;background:#fef3c7;color:#713f12;padding:8px 16px;font:600 14px/1.4 Inter,sans-serif;text-align:center';
    faixa.textContent = 'Demonstração com dados fictícios: as empresas, os valores e os alertas não existem.';
    document.body.prepend(faixa);
    let primeira = null;
    document.querySelectorAll('.nav-tab').forEach(aba => {
      const nome = /aba\('([^']+)'/.exec(aba.getAttribute('onclick') || '')?.[1];
      if (ABAS.includes(nome)) primeira ??= aba;
      else aba.remove();
    });
    document.querySelectorAll('.nav-group').forEach(grupo => {
      if (!grupo.querySelector('.nav-tab')) grupo.remove();
    });
    document.body.style.paddingBottom = '56px';
    primeira?.click();
  });
})();
