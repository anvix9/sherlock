import argparse
from .core import generate

def main():
    parser = argparse.ArgumentParser(description='Get a technical paper card in less than 700 characters. It includes research questions and contributions that anyone can understand.')
    parser.add_argument('input_path', type=str, help='Path to input file/directory')
    
    args = parser.parse_args()
    
    # Call your main function
    generate(args.input_path)

if __name__ == '__main__':
    main()
