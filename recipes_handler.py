import asyncio
import aiohttp

from random import choices
from googletrans import Translator

from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.utils.formatting import (
    Bold, as_list, as_marked_section
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram import Router, types

router = Router()


class OrderCategory(StatesGroup):
    waiting_for_category = State()
    waiting_for_response = State()


@router.message(Command("category_search_random"))
async def category(message: Message, command: CommandObject, state: FSMContext):
    if command.args is None:
        await message.answer(
            "Ошибка: не переданы аргументы"
        )
        return
    async with aiohttp.ClientSession() as session:
        async with session.get(url='https://www.themealdb.com/api/json/v1/1/list.php?c=list') as resp:
            data = await resp.json()
            data = data['meals']
            category_meal = [item['strCategory'] for item in data]

            await state.set_data({'amount': int(command.args)})

            builder = ReplyKeyboardBuilder()
            for date_item in category_meal:
                builder.add(types.KeyboardButton(text=date_item))
            builder.adjust(4)
            await message.answer(
                f"Выберите категорию:",
                reply_markup=builder.as_markup(resize_keyboard=True),
            )
            await state.set_state(OrderCategory.waiting_for_category.state)


@router.message(OrderCategory.waiting_for_category)
async def recipes_list(message: types.Message, state: FSMContext):
    async with aiohttp.ClientSession() as session:
        async with session.get(url=f'https://www.themealdb.com/api/json/v1/1/filter.php?c={message.text}') as resp:
            data = await resp.json()

    amount = await state.get_data()
    data = choices(data["meals"], k=amount.get('amount'))

    name_recipes, id_recipes = [item['strMeal'] for item in data], [item['idMeal'] for item in data]

    translator = Translator()
    ru_recipes = []
    for i in name_recipes:
        i = translator.translate(i, dest='ru')
        ru_recipes.append(i.text)
    await state.set_data({'id_recipes': id_recipes, 'ru_recipes': ru_recipes})
    builder = ReplyKeyboardBuilder()
    builder.add(types.KeyboardButton(text='Показать рецепты'))
    builder.adjust(4)

    response = as_list(
        as_marked_section(
            Bold(f"Как вам такие варианты:"),
            *[f'{k}' for k in ru_recipes],
            marker="🍽️",

        ),
    )
    await message.answer(
        **response.as_kwargs(),
        reply_markup=builder.as_markup(resize_keyboard=True)
    )
    await state.set_state(OrderCategory.waiting_for_response.state)


async def fetch(session, id_recipes):
    async with session.get(url=f'http://www.themealdb.com/api/json/v1/1/lookup.php?i={id_recipes}') as resp:
        data = await resp.json()
        data = data['meals']
        return data


async def translate(translate_data):
    translator = Translator()
    ru_translate = []
    for i in translate_data:
        i = translator.translate(i, dest='ru')
        ru_translate.append(i.text)
    return ru_translate


async def recipe_elements(data):
    data_recipes = data
    keys_ingedients = []
    keys_measure = []
    for i in range(1, 20):
        keys_ingedients.append(f"strIngredient{i}")
        keys_measure.append(f"strMeasure{i}")
    instructions = [data_recipes[0]['strInstructions']]

    ingredient, measure = [], []
    for i in keys_ingedients:
        ingredient.append(data_recipes[0][i])

    for i in keys_measure:
        measure.append(data_recipes[0][i])

    ingredient, measure = filter(None, ingredient), filter(None, measure)

    data_translate = [instructions, ingredient, measure]
    translate_awaitables = [
        translate(i)
        for i in data_translate
    ]
    ru_translate = await asyncio.gather(*translate_awaitables)

    ru_instructions, ru_ingredient, ru_measure = [], [], []
    for i in range(len(data_translate[0])):
        ru_instructions.append(ru_translate[0])
        ru_ingredient.append(ru_translate[1])
        ru_measure.append(ru_translate[2])

    dict_ing = [dict(zip(ru_ingredient[0], ru_measure[0]))]
    return ru_instructions[0], dict_ing


@router.message(OrderCategory.waiting_for_response)
async def detailed_recipes(message: types.Message, state: FSMContext):
    async with aiohttp.ClientSession() as session:
        data = await state.get_data()
        data_id = data['id_recipes']
        data_name = data['ru_recipes']
        for i in range(len(data_name)):
            print(data_name[i])
        fetch_awaitables = [
            fetch(session, i)
            for i in data_id
        ]
        data_recipes = await asyncio.gather(*fetch_awaitables)

        recipe_elements_awaitables = [
            recipe_elements(i)
            for i in data_recipes
        ]

        recipes = await asyncio.gather(*recipe_elements_awaitables)
        ru_instructions = []
        dict_ing = []
        for i in range(len(recipes)):
            ru_instructions.append(recipes[i][0])
            dict_ing.append(recipes[i][1])

        for r in range(len(data_name)):
            name = data_name[r]
            recipe = ru_instructions[r][0]
            ingredients = dict_ing[r][0]
            response = as_list(
                Bold(f'{name}:'
                     f'\n'
                     f'\nРецепт:'
                     f'\n{recipe}'
                     f'\n'
                     f'\nИнгредиенты:'),
                *[
                    f'\n'.join(f'{i}: {m}' for i, m in ingredients.items())
                ],

            )
            await message.answer(
                **response.as_kwargs()
            )
