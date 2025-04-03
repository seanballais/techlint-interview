import * as React from 'react';
import {useState} from 'react';
import {APIError, post, User} from "../../utils/api.ts";

import './Login.css';
import {FormMessage, FormMessageType} from "../../components.tsx";

interface LoginFormState {
    username: string;
    password: string;
    errorMessage?: string;
    isUsernameInputEnabled: boolean;
    isPasswordInputEnabled: boolean;
    isSubmitButtonEnabled: boolean;
}

interface LoginBodyData {
    username: string;
    password: string;
}

interface LoginSuccessJSONResponse {
    data: {
        user: User,
        authorization: {
            access_token: string,
            refresh_token: string
        }
    };
}

interface LoginFailJSONResponse {
    detail: {
        errors: Array<APIError>
    }
}

function Login(): React.ReactNode {
    const [formData, setFormData] = useState<LoginFormState>({
        username: '',
        password: '',
        isUsernameInputEnabled: true,
        isPasswordInputEnabled: true,
        isSubmitButtonEnabled: true
    });

    // Based on:
    // - https://www.w3schools.com/react/react_forms.asp
    function handleChange(event: React.ChangeEvent<HTMLInputElement>): void {
        const name: string = event.target.name;
        const value: string = event.target.value;
        setFormData((values: LoginFormState): LoginFormState => ({
            ...values,
            [name]: value
        }));
    }

    async function handleLogin(event: React.SyntheticEvent<HTMLFormElement, SubmitEvent>): Promise<boolean> {
        event.preventDefault();

        if (formData.username === '' || formData.password === '') {
            return false;
        }

        const bodyData: LoginBodyData = {
            username: formData.username,
            password: formData.password
        };
        setFormData((data: LoginFormState): LoginFormState => ({
            ...data,
            isUsernameInputEnabled: false,
            isPasswordInputEnabled: false,
            isSubmitButtonEnabled: false,
            errorMessage: undefined
        }));

        const response: Response = await post('/login', JSON.stringify(bodyData));
        if (response.ok) {
            const {data}: LoginSuccessJSONResponse = await response.json();
            console.log(data);
        } else {
            const {detail}: LoginFailJSONResponse = await response.json();

            // We already know that there is one error that is returned.
            if (detail.errors[0].code === 'wrong_credentials') {
                console.log(detail.errors[0].code);
                setFormData((data: LoginFormState): LoginFormState => ({
                    ...data,
                    errorMessage: 'Wrong username or password.'
                }));
            }
        }

        setFormData((data: LoginFormState): LoginFormState => ({
            ...data,
            isUsernameInputEnabled: true,
            isPasswordInputEnabled: true,
            isSubmitButtonEnabled: true
        }));

        return false;
    }

    return (
        <div className='form-container'>
            <h1>Login</h1>
            <form className='login' onSubmit={handleLogin}>
                <FormMessage type={FormMessageType.Error}
                             message={formData.errorMessage}/>
                <div className='form-group'>
                    <label htmlFor='username'>Username</label>
                    <input type='text' placeholder='Username' name='username'
                           onChange={handleChange}
                           disabled={!formData.isUsernameInputEnabled}
                           required/>
                </div>
                <div className='form-group'>
                    <label htmlFor='password'>Password</label>
                    <input type='password' placeholder='Password'
                           name='password'
                           onChange={handleChange}
                           disabled={!formData.isUsernameInputEnabled}
                           required/>
                </div>
                <button type='submit'
                        disabled={!formData.isUsernameInputEnabled}>Login
                </button>
            </form>
        </div>
    )
}

export default Login;
