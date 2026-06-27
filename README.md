# pet-source_tools - PangYa import/export script for Blender 2.80+
É um fork de https://github.com/retreev/io_scene_mpet

# Disclaimer
Não sei nada de Modelagem 3D, então tudo que fiz foi baseado no fork original, e pesquisas no google.
Sou novato no Blender ou qualquer outro software de modelagem 3D.

# PangYa File Format
Para começa usei essa documentação: https://github.com/retreev/Documentation/blob/master/pc/file-formats/pet.md.
E fui ajeitando e adicionando novos valores para todas as versão dos arquivos que faltavam.

## Status

  * Funcionando com Blender 2.80+, testado nas versões 3.4, 4.4 e 5.0.
  
  # Import Puppet
  * Carrega todos os arquivos .pet, .apet, .bpet, .mpet de todas as versões do PangYa do PC.
  * Carrega os especular materiais.
  * Carrega collision box.
  * Carrega as texturas.
  * Carrega as animações.
  * Carrega os motions. "São os intervalos de quadros na animação com o metôdo de conexão e o tempo de conexão para o próximo motion"
  * Carrega os frames. "Tem o índice do quadro da animação para aplicar os scripts de animação"
  * Carrega os face animations. "São os materiais de textura, tem o nome do material e o nome da textura"
  * Carrega as câmeras .apet dos personagens e junta com a animação do personagem que foi carregado anteriormente.
  * Carrega as câmeras .apet que não são dos personagens separadas.
  * Carrega os Specular Materials Filter que é usado no Course Abbot Mine.
  * Abre mais de um arquivo de uma vez, só selecionar com shift(depende do sistema operacional), Os .mpet se já tiver carregado um .bpet(default) ele usar o bone do .bpet(default), se não usa o bone do .mpet.
  * Faz um hook no frame_change para aplicar os scripts dos frames, como o facetexture, hide/show bone e club.

  # Export Puppet
  * Salva nas versões 1.0, 1.1, 1.2 e 1.3.
  * Salva no formato .pet, .apet, .bpet e .mept.
  * Para salvar precisa selecionar um objeto do tipo MESH com um modificador de armação de ossos, com excessão dos formatos .apet e .bpet.
  * Para salvar um .apet e .bpet só precisa selecionar um objeto de armação de ossos.

  # Import GBIN
  * Carrega todos os aquivos .gbin, .sgbin, .aibin, .sbin de todas as versões do PangYa do PC.
  * Carrega o Puppet base.
  * Carrega os Puppets de enfeite.
  * Carrega as Câmeras.
  * Carrega os Pontos(Pin, Tee, Sun, Moon, Global Light, start PSQ).
  * Carrega as Áreas(Oceano(Som), Lago(Som), NPC spawn, Extra(Approach Pang Battle, Approach e Short Game), Efeitos, Troca de Ventos, Vortex e etc).
  * Carrega os Nodes(Auto(A.I), O.B, A.I Grand Prix, Oceano, Lago e etc).
  * Carrega os Novos elementos que é o Tee e os Pins do Grand Zodiac.
  * Carrega os Vertex Color Filter do elemento base do gbin.
  * Carrega o .sbin(Shadow Map) mapa de sombras pré-calculadas. 

  # Export GBIN
  * Salva nas versões 112, 113 e 114.
  * Salva no formato .gbin, .sgbin, .aibin, .sbin.
  * Para salvar precisa selecionar o collection com o nome do .gbin.
  * Os formatos .sgbin e .aibin só são salvos na versão 114.
  * O .sbin(Shadow Map). "Porém as sombras não estão com precisão e definição iguais a do pangya mas é aceitável"

## Compile o blender com a escala no bone edit
Para ter toda a precisão dos objetos 3d do pangya que tenha escala na matrix de descanso do osso.

Veja o próprio site do blender para ver como se compila ele: https://developer.blender.org/docs/handbook/building_blender/

Depois que compilou a primeira vez faça o patch das alterações e compile para ter o blender com a escala no bone edit.

# Patch para versão 5.1(Alpha)
```
git checkout 0f37df9aaa0c2e9b08db648299c6a1b14f683e47
git checkout -b temp-patch
git am "caminho do arquivo"/changes_in_blender_to_work_with_rest_pose_matrix_pangya.patch
```

Você pode fazer a compilação do blender ela é a versão 5.1(Alpha)
```
make
```

Ou fazer o merge com o main.

```
git checkout main
git merge temp-patch
git branch -D temp-patch
```

Mas se você quiser fazer o merge com a main, provável que vai ter conflitos, então você vai ter que resolver eles se quiser usar versões mais rescentes do blender, se eu não tiver postado atualizações do arquivo de patch.

# Prováveis erros
No script 01_install_pillow.py se o blender não tiver permissão para instalar o pillow no python do blender execute o blender como administrado.

## Usage
Clone this git repository into:

  * Windows: `%APPDATA%\Blender Foundation\Blender\2.80+(3.4)\scripts\addons\pet-source_tools`
  * Linux: `$HOME/.blender/2.80+(3.4)/scripts/addons/pet-source_tools`

### What if I don't have git?
Hit [download zip](https://github.com/Acrisio-Filho/pet-source_tools/archive/refs/heads/master.zip) and extract it such that you have a folder named `pet-source_tools` in your `addons` directory (listed above) and that folder contains `__init__.py` (and neighboring files, of course.)
