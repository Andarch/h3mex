from enum import IntEnum


class ExtendedEvents:
    READ_RAW = False

    class Type(IntEnum):
        Hero = 0
        Player = 1
        Town = 2
        Quest = 3

    class Action(IntEnum):
        IfThenElseIf = 1
        SetVariableBasedOnCondition = 2
        ModifyVariable = 3
        ResourcesReward = 4
        RemoveCurrentObject_FinishQuest = 5
        MessageWithReward = 6
        QuestAction = 7
        CreaturesReward = 8
        ArtifactReward = 9
        BuildTownStructure = 10
        SetQuestHintAndLogEntry = 11
        Question = 12
        IfThenElse = 13
        AddCreaturesToHire = 14
        SpellReward = 15
        ExperienceReward = 16
        SpellPointsReward = 17
        MovementPointsReward = 18
        PrimarySkillsReward = 19
        SecondarySkillsReward = 20
        LuckReward = 21
        MoraleReward = 22
        Combat = 23
        ExecuteEvent = 24
        WarMachineReward = 25
        SpellbookReward = 26
        DisableEvent = 27
        Cycle = 28
        ShowMessage = 29

    class VariableMode(IntEnum):
        InitialValue = 0
        ImportFromPrevious = 1

    class VariableOperation(IntEnum):
        Add = 0
        Subtract = 1
        Set = 2

    class ExpressionOperandMode(IntEnum):
        Integer = 0
        Expression = 1

    class ExpressionType(IntEnum):
        IntegerValue = 0
        VariableValue = 1
        InvertSign = 2
        Add = 3
        Subtract = 4
        Resource = 5
        Multiply = 6
        Divide = 7
        Remainder = 8
        CreatureCount = 9
        CurrentDifficultyLevel = 10
        DifficultyLevel = 11
        CurrentDate = 12
        CurrentHeroExperience = 13
        CurrentHeroLevel = 14
        PrimarySkill = 15
        RandomNumber = 16
        ArtifactCount = 17

    class ExpressionPlayer(IntEnum):
        Red = 0
        Blue = 1
        Tan = 2
        Green = 3
        Orange = 4
        Purple = 5
        Teal = 6
        Pink = 7
        Current = 255

    class ExpressionDifficultyLevel(IntEnum):
        Pawn = 0
        Knight = 1
        Rook = 2
        Queen = 3
        King = 4

    class ConditionType(IntEnum):
        BooleanValue = 0
        And = 1
        Or = 2
        LessThan = 3
        GreaterThan = 4
        Equal = 5
        Not = 6
        HeroHasArtifact = 7
        GreaterThanOrEqual = 8
        LessThanOrEqual = 9
        NotEqual = 10
        CurrentHero = 11
        HeroAffiliation = 12
        HeroClass = 13
        MonsterDefeatedByPlayer = 14
        HeroDefeatedByPlayer = 15
        HeroSecondarySkill = 16
        PlayerDefeated = 17
        TownControlledByPlayer = 18
        PlayerIsHuman = 19
        PlayerStartingTown = 20

    class ConditionPlayer(IntEnum):
        Red = 0
        Blue = 1
        Tan = 2
        Green = 3
        Orange = 4
        Purple = 5
        Teal = 6
        Pink = 7

    class ConditionPlayerOrCurrent(IntEnum):
        Current = -1
        Red = 0
        Blue = 1
        Tan = 2
        Green = 3
        Orange = 4
        Purple = 5
        Teal = 6
        Pink = 7

    class ConditionDefeatingPlayer(IntEnum):
        Any = -2
        Current = -1
        Red = 0
        Blue = 1
        Tan = 2
        Green = 3
        Orange = 4
        Purple = 5
        Teal = 6
        Pink = 7

    class HeroAffiliationLocation(IntEnum):
        CurrentHero = -2
        AnywhereCurrentPlayer = -1
        AnywherePlayer1 = 0
        AnywherePlayer2 = 1
        AnywherePlayer3 = 2
        AnywherePlayer4 = 3
        AnywherePlayer5 = 4
        AnywherePlayer6 = 5
        AnywherePlayer7 = 6
        AnywherePlayer8 = 7

    class RewardOperation(IntEnum):
        Give = 0
        Take = 1

    class SpellPointsOperation(IntEnum):
        Give = 0
        Take = 1
        Nullify = 2
        Set = 3
        Replenish = 4

    class MovementPointsOperation(IntEnum):
        Give = 0
        Take = 1
        Nullify = 2
        Set = 3
        Replenish = 4

    class TownCreatureLevel(IntEnum):
        Level1 = 0
        Level2 = 1
        Level3 = 2
        Level4 = 3
        Level5 = 4
        Level6 = 5
        Level7 = 6
        Level7B = 7

    class BuildStructureTownType(IntEnum):
        Castle = 0
        Rampart = 1
        Tower = 2
        Inferno = 3
        Necropolis = 4
        Dungeon = 5
        Stronghold = 6
        Fortress = 7
        Conflux = 8
        Cove = 9
        Factory = 10
        Bulwark = 11
        Common = 65535

    class QuestLogImageType(IntEnum):
        Artifact = 0
        SpellScroll = 1
        Creatures = 2
        Resources = 3
        PrimarySkill = 4
        SecondarySkill = 5
        Level = 6
        PlayerFlag = 7
        Hero = 8
        HeroOnMap = 9
        MonsterOnMap = 10

    class QuestLogImageValueMode(IntEnum):
        Integer = 0
        Variable = 1

    class MessageImageType(IntEnum):
        ResourcesPlus = 0
        Artifact = 1
        Spell = 2
        PlayerFlag = 3
        Luck = 4
        Morale = 5
        Experience = 6
        SecondarySkill = 7
        Creatures = 8
        PrimarySkill = 9
        SpellPoints = 10
        MovementPoints = 11
        GoldSmallPlus = 12
        ResourcesMinus = 13
        ResourcesPerDay = 14
        SpellScroll = 15
        LevelPlusOne = 16
        CreaturesSimple = 17
        ResourcesSimple = 18
        PrimarySkillPlus = 19
        GoldSmallMinus = 20
        GoldSmall = 21
        GoldSmallPerDay = 22
        BuildingCastle = 1000
        BuildingRampart = 1001
        BuildingTower = 1002
        BuildingInferno = 1003
        BuildingNecropolis = 1004
        BuildingDungeon = 1005
        BuildingStronghold = 1006
        BuildingFortress = 1007
        BuildingConflux = 1008
        BuildingCove = 1009
        BuildingFactory = 1010
        BuildingBulwark = 1011

    class MessageImageValueMode(IntEnum):
        Integer = 0
        Variable = 1

    class QuestionImageMode(IntEnum):
        NoImages = 0
        SelectionCantExit = 1
        SelectionCanExit = 2
        SpecifyImages = 3
