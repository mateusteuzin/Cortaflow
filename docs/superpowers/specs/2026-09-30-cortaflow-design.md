# CortaFlow: Master Prompt de Produto e Design

## Objetivo

Transforme o CortaFlow existente em um SaaS profissional de gestao para barbearias. Entregue uma experiencia coerente entre painel, agendamento publico, autenticacao e e-mails transacionais. A qualidade sera demonstrada por fluxos completos, legibilidade, consistencia, acessibilidade e verificacao visual; nao por promessas de melhoria percentual.

Projeto: `C:/Users/ma266/Downloads/Cortaflow-main/Cortaflow-main`.

Stack existente: FastAPI, PostgreSQL, HTML, CSS e JavaScript. Preserve essa stack e os contratos existentes. Leia as instrucoes locais antes de editar. Preserve mudancas do usuario.

## Direcao de Design

Use uma identidade operacional contemporanea: preto grafite, branco, cinzas neutros e o amarelo CortaFlow como acento. Verde, vermelho e azul comunicam estados distintos, acompanhados de texto ou simbolos. A marca deve ser reconhecivel, enquanto os dados e a agenda devem ser a prioridade.

Utilize uma familia sans consistente no produto, titulos compactos, pesos moderados e escala fixa de tipografia. Adote espacos de 4, 8, 12, 16, 24 e 32 px; controles de pelo menos 44 px de altura nas interacoes de toque; bordas discretas; raios entre 4 e 8 px para controles e itens; sombras apenas em elementos sobrepostos. Defina tokens semanticos para superficies, texto, bordas, foco, estados e acoes, incluindo modo claro e escuro.

Evite excesso de caixas, grandes saudacoes no painel, slogans nos formularios, letras espacadas, titulos gigantes, brilhos, gradientes decorativos e efeitos que dificultem a leitura. Prefira tabelas, linhas, calendarios e secoes sem molduras repetidas. Use os icones da biblioteca existente; se necessario, adote uma unica biblioteca estabelecida.

Referencias locais: `.agents/design-references/awesome-design-systems`. Skills: `.agents/skills`. Use referencias para fundamentar componentes e acessibilidade; defina a identidade CortaFlow sem copiar uma marca externa.

## Etapa 1: Painel e Agenda

Arquivos principais: `app/static/index.html`, `app/static/styles.css`, `app/static/app.js`.

Comece pela navegacao, cabecalho, Resumo do dia e Agenda. Depois estenda os mesmos componentes para Clientes, Equipe, Servicos, Produtos, Financeiro, Insights, Minha assinatura e Minha conta.

O resumo deve mostrar a data, indicadores uteis, proximos atendimentos e uma acao principal de novo agendamento. Cada indicador deve explicitar seu periodo. Remova hierarquias duplicadas e espacos vazios sem funcao.

A agenda deve facilitar localizar um atendimento, filtrar profissionais, mudar a data e abrir os detalhes. Destaque o dia selecionado, horario, cliente, servico, profissional e status. Mantenha os filtros ao navegar quando o comportamento existente permitir. No celular, use uma apresentacao diaria ou lista legivel, evitando comprimir sete colunas.

Padronize formularios, botoes, menus, modais, tabelas, notificacoes e estados de carregamento, vazio e erro. Preserve IDs, atributos de eventos, permissoes e contratos de API. Validacoes devem indicar o campo e como corrigir. Acoes destrutivas precisam explicar a consequencia antes da confirmacao.

## Etapa 2: Agendamento Publico

Arquivos principais: `app/static/cliente.html`, `app/static/cliente.css`, `app/static/cliente.js`.

O primeiro viewport deve identificar a barbearia e permitir iniciar a reserva. Use logo, nome e imagens reais ja existentes quando apropriadas. Priorize a reserva; evite obrigar o cliente a atravessar um hero para acessar horarios.

Mantenha o fluxo existente de selecao de servico, profissional, data e horario, seguido dos dados do cliente e revisao. Mostre preco e duracao antes de continuar. Ao mudar o servico, profissional ou data, invalide selecoes dependentes que deixaram de ser validas.

Apresente servicos e profissionais como escolhas acessiveis, com estado selecionado claro. Datas e horarios precisam de estados disponivel, selecionado, indisponivel e carregando. Explique quando nao houver horarios e ofereca mudar a data ou o profissional.

Preserve escolhas validas ao voltar. Na revisao, exiba barbearia, servico, profissional, data, horario e valor. Impeca envio duplicado durante a requisicao. Se o horario for ocupado por outra pessoa, explique o conflito e permita escolher outro horario sem perder os dados pessoais.

A confirmacao deve apresentar o resultado salvo pelo servidor e as acoes de consulta existentes. Diferencie reserva confirmada de notificacao enviada. Nunca declare entrega de WhatsApp ou e-mail quando o sistema apenas iniciou ou tentou o envio. Preserve isolamento por slug e a regra de bloqueio de conflito no banco.

## Etapa 3: E-mails

Arquivo principal: `app/services/email.py`.

Unifique o visual dos e-mails de verificacao de conta, redefinicao de senha, convite de profissional, assinatura e eventos de agendamento para cliente, proprietario e profissional.

Cada mensagem deve ter remetente identificavel, assunto especifico, preheader util, titulo direto, dados relevantes e uma acao principal. Para agendamentos, mostre nome da barbearia, servico, profissional, data, horario, preco quando aplicavel e codigo. Mostre expiracao e uso unico apenas nos fluxos que realmente implementam essas regras.

Use HTML com tabelas de apresentacao e estilos inline, largura maxima de 600 px, fontes seguras, contraste legivel, textos alternativos e versao em texto simples. O conteudo deve continuar compreensivel sem imagens. Escape todos os dados interpolados do usuario e preserve a codificacao dos links.

Preserve o envio pelo Resend, deduplicacao, destinatarios autorizados e isolamento entre barbearias. Falha de notificacao nao deve desfazer uma reserva. Teste com provedor simulado; nao envie mensagens reais durante a verificacao.

## Etapa 4: Acesso e Paginas Publicas

Revise login, criacao de conta, recuperacao de senha e a landing efetivamente servida por `app/main.py`. O projeto contem mais de uma landing: identifique as rotas antes de editar. Nao altere valores, periodos de teste ou condicoes comerciais sem autorizacao.

Mantenha a identidade comum, mas adapte a densidade ao contexto. Formularios devem ter rotulos persistentes, preenchimento automatico, erros claros e feedback de processamento. Nunca use metricas, depoimentos, funcionalidades ou promessas inventadas.

## Verificacao Obrigatoria

Execute os testes relevantes de agenda, agendamento publico, e-mails, acesso de profissionais e seguranca. Use fixtures e APIs simuladas para verificacao local quando nao houver banco configurado; identifique explicitamente esse modo.

Verifique visualmente em 390x844, 768x1024 e 1440x900, incluindo modo claro e escuro no painel. Confira ausencia de rolagem horizontal indevida, textos cortados, sobreposicoes, imagens ausentes e erros no console. Percorra navegacao por teclado, selecao de servico, profissional, data, horario, revisao, retorno e confirmacao, incluindo falha de rede e conflito de horario.

Valide contraste WCAG AA, foco visivel, rotulos acessiveis e reducao de movimento. Inspecione e-mails com imagens bloqueadas e em largura de celular. Previews de navegador nao comprovam compatibilidade com todos os clientes de e-mail: registre essa limitacao.

## Forma de Executar

Implemente por etapas revisaveis. Primeiro entregue painel e agenda com tokens compartilhados; depois agendamento; depois e-mails; finalmente acesso e paginas publicas. Cada etapa deve produzir software utilizavel, testes pertinentes e capturas de tela. Nao marque etapas futuras como concluidas.

Inicie um servidor local para a verificacao e entregue o endereco. Ao finalizar, informe arquivos alterados, fluxos testados, limitacoes reais e tarefas restantes. Nao publique, nao modifique credenciais e nao execute migracoes no banco de producao como parte do redesign.
