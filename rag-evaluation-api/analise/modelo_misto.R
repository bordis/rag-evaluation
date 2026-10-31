# Modelo misto de H1 a H3 sobre o CSV de GET /api/admin/studies/{id}/export.csv.
# Uso: Rscript analise/modelo_misto.R estudo.csv
#
# Cada efeito e uma regressao logistica so com intercepto, por rodada: testar intercepto = 0 equivale
# a testar 50% com avaliador e documento como efeitos aleatorios. Rodadas "nenhuma" ficam de fora.

library(lme4)

args <- commandArgs(trailingOnly = TRUE)
dados <- read.csv(args[1])

vencedoras <- subset(dados, venceu == 1 & nenhuma_correta == 0)
vencedoras$h1 <- vencedoras$docling
vencedoras$h2 <- vencedoras$avancado
vencedoras$h3 <- as.integer(vencedoras$docling == vencedoras$avancado)

for (efeito in c("h1", "h2", "h3")) {
  formula_efeito <- as.formula(paste(efeito, "~ 1 + (1 | avaliador) + (1 | documento)"))
  modelo <- glmer(formula_efeito, data = vencedoras, family = binomial)
  estimativa <- fixef(modelo)[["(Intercept)"]]
  ic <- confint(modelo, parm = "(Intercept)", method = "Wald")

  cat("\n==", efeito, "==\n")
  print(summary(modelo)$coefficients)
  cat("Taxa estimada:", round(plogis(estimativa), 3), "\n")
  cat("IC 95%:", round(plogis(ic), 3), "\n")
}

# Fadiga: a chance de escolher a recuperacao avancada muda ao longo do ciclo?
fadiga <- glmer(
  h2 ~ scale(ordem) + (1 | avaliador) + (1 | documento),
  data = vencedoras,
  family = binomial
)
cat("\n== Fadiga (h2 ~ ordem) ==\n")
print(summary(fadiga)$coefficients)
